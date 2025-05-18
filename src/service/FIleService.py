import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from frontend import *
from playwright.async_api import async_playwright
from typing import Union

def is_valid_url(input_str: str) -> bool:
    """Check if input is a valid URL and not a YouTube link."""
    try:
        result = urlparse(input_str)
        is_url = all([result.scheme, result.netloc])
        is_youtube = "youtube.com" in result.netloc or "youtu.be" in result.netloc
        return is_url and not is_youtube
    except Exception:
        return False

async def fetch_page_with_playwright(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        content = await page.content()
        await browser.close()
        return content

def extract_text_from_html(html: str) -> str:
    """Extract visible text from raw HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style']):
        tag.decompose()
    return soup.get_text(separator=' ', strip=True)

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file."""
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

async def extract_text(input_data: Union[str, bytes]) -> str:
    """
    Extracts text from a URL (rendered HTML) or local PDF file.
    """
    if isinstance(input_data, str) and is_valid_url(input_data):
        html = await fetch_page_with_playwright(input_data)  # <-- await here
        return extract_text_from_html(html)  # no need for await, sync func
    elif isinstance(input_data, str) and input_data.lower().endswith('.pdf'):
        # PDF extraction is sync, so just call it directly
        return extract_text_from_pdf(input_data)
    else:
        raise ValueError("Unsupported input: must be a valid URL or a PDF file path")


# Example usage
if __name__ == "__main__":
    text = extract_text("https://meteoinfo.ru/forecasts/russia/moscow-area/moscow")
    print(text)

    # From PDF
    text = extract_text("../resources/Mage_Wars_Rules_Supplement.pdf")
    print(text)

