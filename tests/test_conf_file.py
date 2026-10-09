from app.core.conf_file import ConfFile, parse_value


def test_parse_types():
    """Comprueba la conversión de texto a bool, int, float, lista y texto."""
    assert parse_value("true") is True
    assert parse_value("12") == 12
    assert parse_value("0.5") == 0.5
    assert parse_value("0.1, 0.6") == [0.1, 0.6]
    assert parse_value("0x0300") == "0x0300"
    assert parse_value("192.168.0.3") == "192.168.0.3"
    assert parse_value('"#111827"') == "#111827"


def test_write_keeps_comments(tmp_path):
    """Comprueba que escribir claves conserva los comentarios del archivo."""
    path = tmp_path / "sample.conf"
    path.write_text("# comentario\n[plc]\n# la ip\nip = 1.1.1.1\n", encoding="utf-8")
    conf = ConfFile(path)
    conf.set("plc", "ip", "192.168.0.3")
    conf.set("plc", "new", 5)
    text = path.read_text(encoding="utf-8")
    assert "# comentario" in text and "# la ip" in text
    assert "ip = 192.168.0.3" in text and "new = 5" in text
    assert ConfFile(path).get("plc", "new") == 5


def test_remove_section(tmp_path):
    """Comprueba que se borra solo la sección indicada."""
    path = tmp_path / "lines.conf"
    path.write_text("[line_1]\na = 0, 0\n\n[line_2]\na = 1, 1\n\n[other]\nx = 1\n", encoding="utf-8")
    conf = ConfFile(path)
    conf.remove_section("line_2")
    assert ConfFile(path).sections() == ["line_1", "other"]
