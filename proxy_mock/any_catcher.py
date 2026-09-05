from proxy_mock.app import create_app

app = create_app()

if __name__ == "__main__":
    import sys

    from proxy_mock.cli import main

    sys.exit(main())
