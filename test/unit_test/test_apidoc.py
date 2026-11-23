import apidoc


def test_api_reference_is_up_to_date():
    """resources/generated/API-REFERENCE.md must match the routes and the JSON schema"""
    current = apidoc.OUTPUT_FILE.read_text(encoding="utf-8") if apidoc.OUTPUT_FILE.exists() else ""
    assert current == apidoc.generate(), \
        "resources/generated/API-REFERENCE.md is not up to date. Regenerate it with: ./admin.sh apidoc"


def test_all_routes_have_a_docstring():
    assert "*(no docstring)*" not in apidoc.generate()
