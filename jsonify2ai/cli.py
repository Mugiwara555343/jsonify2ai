import typer

app = typer.Typer(help="jsonify2ai: ingest → embed → store → retrieve")


# subcommand placeholders
@app.command()
def version():
    """Show version."""
    import importlib.metadata as md

    print(md.version("jsonify2ai"))


if __name__ == "__main__":
    app()
