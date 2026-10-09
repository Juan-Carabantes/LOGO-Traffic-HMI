import configparser
import re
import threading
from pathlib import Path


_RE_INT = re.compile(r"^[-+]?\d+$")
_RE_DECIMAL = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")
_RE_KEY = re.compile(r"^(\s*)([^=:\s#;\[][^=:]*?)(\s*[=:]\s*)(.*)$")


def parse_value(text):
    """Convierte el texto de un .conf al tipo Python más adecuado.

    true/false -> bool | 12 -> int | 0.5 -> float
    0.1, 0.6   -> list[float] (solo si todos los elementos son numericos)
    "texto"    -> str sin comillas | 0x0300 se conserva como texto
    """
    if text is None:
        return None
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]

    lowercase = value.lower()
    if lowercase in ("true", "yes", "on", "si", "sí"):
        return True
    if lowercase in ("false", "no", "off"):
        return False
    if _RE_INT.match(value):
        return int(value)
    if _RE_DECIMAL.match(value):
        return float(value)
    if "," in value:
        parts = [p.strip() for p in value.split(",")]
        if parts and all(_RE_DECIMAL.match(p) for p in parts):
            return [float(p) for p in parts]
    return value


def serialize_value(value):
    """Convierte un valor Python al texto que se escribe en el .conf."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{round(value, 6):g}" if abs(value) < 1e6 else repr(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(serialize_value(v) for v in value)
    if value is None:
        return ""
    return str(value)


class ConfFile:
    """Archivo .conf con secciones que conserva comentarios, orden y formato.

    Las escrituras modifican solo la línea afectada del archivo en disco.
    """

    def __init__(self, path):
        """Abre el archivo indicado y carga su contenido."""
        self.path = Path(path)
        self._lock = threading.RLock()
        self.parser = None
        self.reload()

    # --- Lectura ---

    def reload(self):
        """Vuelve a leer el archivo desde disco; si no existe queda vacío."""
        with self._lock:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            if self.path.exists():
                parser.read(self.path, encoding="utf-8")
            self.parser = parser

    def sections(self):
        """Devuelve la lista de secciones del archivo."""
        return self.parser.sections()

    def has_section(self, section):
        """Indica si la sección existe."""
        return self.parser.has_section(section)

    def section(self, section):
        """Devuelve un dict {clave: valor_convertido} de la sección."""
        if not self.parser.has_section(section):
            return {}
        return {k: parse_value(v) for k, v in self.parser.items(section)}

    def section_text(self, section):
        """Igual que section() pero sin convertir tipos (todo como texto)."""
        if not self.parser.has_section(section):
            return {}
        return {k: parse_value_text(v) for k, v in self.parser.items(section)}

    def as_dict(self):
        """Devuelve todo el archivo como {sección: {clave: valor}}."""
        return {s: self.section(s) for s in self.parser.sections()}

    def find_section(self, key):
        """Devuelve la primera sección que contiene la clave, o None."""
        key = key.lower()
        for section in self.parser.sections():
            if self.parser.has_option(section, key):
                return section
        return None

    def get(self, section, key, default=None):
        """Lee una clave convertida a su tipo Python, o devuelve default si no existe."""
        if self.parser.has_option(section, key):
            return parse_value(self.parser.get(section, key))
        return default

    def get_text(self, section, key, default=None):
        """Lee una clave como texto sin convertir, o devuelve default si no existe."""
        if self.parser.has_option(section, key):
            return parse_value_text(self.parser.get(section, key))
        return default

    # --- Escritura ---

    def set(self, section, key, value):
        """Guarda un valor en memoria y en disco, conservando comentarios, orden y espacios."""
        text = serialize_value(value)
        with self._lock:
            if not self.parser.has_section(section):
                self.parser.add_section(section)
            self.parser.set(section, key, text)
            self._write_line(section, key, text)

    def remove_section(self, section):
        """Borra una sección completa (encabezado, claves y comentarios que le siguen)."""
        with self._lock:
            if not self.parser.has_section(section):
                return
            self.parser.remove_section(section)

            # Copia las líneas saltando las de la sección y las líneas en blanco previas
            lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
            result, inside = [], False
            for line in lines:
                clean = line.strip()
                if clean.startswith("[") and clean.endswith("]"):
                    inside = clean[1:-1].strip() == section
                    if inside:
                        while result and not result[-1].strip():
                            result.pop()
                        continue
                if not inside:
                    result.append(line)
            self._save(result)

    def _write_line(self, section, key, text):
        """Reemplaza la línea de la clave en el archivo o la agrega al final de su sección."""
        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        current_section = None
        last_section_line = None
        lower_key = key.lower()

        # Busca la clave dentro de la sección y recuerda su última línea con contenido
        for i, line in enumerate(lines):
            clean = line.strip()
            if clean.startswith("[") and clean.endswith("]"):
                current_section = clean[1:-1].strip()
                if current_section == section:
                    last_section_line = i
                continue
            if current_section != section:
                continue
            if clean and not clean.startswith(("#", ";")):
                last_section_line = i
            match = _RE_KEY.match(line)
            if match and match.group(2).strip().lower() == lower_key:
                indent, name, separator, _ = match.groups()
                lines[i] = f"{indent}{name}{separator.rstrip()} {text}".rstrip()
                self._save(lines)
                return

        # La clave no existe: se agrega al final de la sección o en una sección nueva
        new = f"{key} = {text}".rstrip()
        if last_section_line is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([f"[{section}]", new])
        else:
            lines.insert(last_section_line + 1, new)
        self._save(lines)

    def _save(self, lines):
        """Escribe las líneas en un archivo temporal y lo reemplaza de forma atomica."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        # newline="\n" mantiene el mismo formato en Windows y Linux (evita mezclar CRLF/LF)
        with open(temp, "w", encoding="utf-8", newline="\n") as file:
            file.write("\n".join(lines) + "\n")
        temp.replace(self.path)


def parse_value_text(text):
    """Quita comillas envolventes y espacios, sin convertir tipos."""
    value = (text or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value
