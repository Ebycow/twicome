def test_main_exports_app():
    import main

    assert main.app is not None
