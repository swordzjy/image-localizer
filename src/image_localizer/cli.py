from __future__ import annotations

from pathlib import Path

import typer

from image_localizer.env import load_dotenv
from image_localizer.ocr.registry import get_ocr_engine, list_ocr_engines
from image_localizer.pipeline import run_pipeline
from image_localizer.scrapers.registry import list_scrapers
from image_localizer.translation.registry import get_translator, list_translators

app = typer.Typer(help="Image localization pipeline: scrape, OCR, translate, edit.")


@app.callback()
def _bootstrap() -> None:
    """Load environment variables from a project-local ``.env`` before any command.

    Existing environment variables take precedence, so exported values are never
    overwritten by the file.
    """
    load_dotenv()


@app.command()
def localize(
    target_lang: str = typer.Argument(..., help="Target language code, e.g. fr, es, de."),
    url: str | None = typer.Option(None, "--url", "-u", help="Product page URL to scrape."),
    image_dir: Path | None = typer.Option(None, "--image-dir", "-d", help="Local directory of source images. Skip scraping/downloading."),
    output: Path = typer.Option(Path("./out"), "--output", "-o", help="Output directory."),
    scraper: str = typer.Option("auto", "--scraper", "-s", help=f"Scraper to use: {', '.join(list_scrapers())}, or auto."),
    ocr: str = typer.Option("easyocr", "--ocr", help=f"OCR engine: {', '.join(list_ocr_engines())}."),
    translator: str = typer.Option("claude", "--translator", "-t", help=f"Translator: {', '.join(list_translators())}."),
    source_lang: str | None = typer.Option(None, "--source-lang", help="Optional source language hint."),
) -> None:
    """Run the full image localization pipeline."""
    if not url and not image_dir:
        raise typer.BadParameter("Either --url or --image-dir must be provided.")
    if url and image_dir:
        raise typer.BadParameter("Provide either --url or --image-dir, not both.")
    if image_dir and not image_dir.is_dir():
        raise typer.BadParameter(f"--image-dir is not a directory: {image_dir}")

    scraper_name = None if scraper == "auto" else scraper
    ocr_engine = get_ocr_engine(ocr)
    translator_engine = get_translator(translator)

    run_pipeline(
        url=url,
        image_dir=image_dir,
        target_lang=target_lang,
        output_dir=output,
        scraper_name=scraper_name,
        ocr_engine=ocr_engine,
        translator=translator_engine,
    )


@app.command()
def list_plugins() -> None:
    """List available scrapers, OCR engines, and translators."""
    typer.echo("Scrapers: " + ", ".join(list_scrapers()))
    typer.echo("OCR engines: " + ", ".join(list_ocr_engines()))
    typer.echo("Translators: " + ", ".join(list_translators()))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
