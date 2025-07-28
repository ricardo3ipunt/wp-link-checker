import http
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import csv
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
WP_URL = ""
SITEMAP_URL = f"{WP_URL}/wp-sitemap.xml"


def get_urls_from_sitemap(sitemap_url):
    """Gets all page URLs from a WordPress sitemap, including nested sitemaps."""
    urls = []
    try:
        r = requests.get(sitemap_url, timeout=10, verify=False)
        r.raise_for_status()
        sp = BeautifulSoup(r.text, "xml")
        
        # Check if it's a sitemap
        sitemap_elements = sp.find_all("sitemap")
        
        if sitemap_elements:
            # Recursively get URLs from each nested sitemaps
            for sitemap in sitemap_elements:
                loc_tag = sitemap.find("loc")
                if loc_tag:
                    nested_sitemap_url = loc_tag.text
                    print(f"   -> Found nested sitemap: {nested_sitemap_url}")
                    urls.extend(get_urls_from_sitemap(nested_sitemap_url))
        else:
            # It's a regular sitemap, get all URL locations
            url_locs = sp.find_all("loc")
            urls = [url.text for url in url_locs]
            
    except requests.RequestException as e:
        print(f"Error accessing sitemap {sitemap_url}: {e}")
    except Exception as e:
        print(f"Error processing sitemap {sitemap_url}: {e}")
        
    return urls


def check_image_status(img_url):
    """Check if an image is accessible or broken."""
    try:
        response = requests.head(
            img_url, timeout=5, allow_redirects=False, verify=False
        )
        status_code = response.status_code
        
        if status_code == 200:
            return "OK", f"{status_code}"
        elif status_code == 301:
            return "PROBABLY_OK", f"{status_code}"
        else:
            return "BROKEN", f"{status_code}"

    except requests.RequestException:
        return "BROKEN", "Connection failed"


def check_images_on_page(page_url):
    """Finds and checks the status of all images on a given URL."""
    results = []

    try:
        response = requests.get(page_url, timeout=10, verify=False)
        soup = BeautifulSoup(response.text, "lxml")
        img_tags = soup.find_all("img")

        print(f"   -> Found {len(img_tags)} images on this page")

        for img_tag in img_tags:
            img_src = img_tag.get("src")
            if not img_src:
                continue

            img_url = urljoin(page_url, img_src)
            img_alt = img_tag.get("alt", "No alt text")

            status, http_code = check_image_status(img_url)

            if status == "BROKEN" or status == "PROBABLY_OK":
                if status == "BROKEN":
                    print(f"   -> ❌ Broken: {img_url} (Error: {http_code})")
                else:
                    print(f"   -> Probably OK (Manual check required): {img_url} (Error: {http_code})")
                results.append(
                    {
                        "page_url": page_url,
                        "image_url": img_url,
                        "image_alt": img_alt,
                        "status": status,
                        "http_code": http_code,
                        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

    except requests.RequestException as e:
        print(f"Could not scan page {page_url}: {e}")
        results.append(
            {
                "page_url": page_url,
                "image_url": "N/A",
                "image_alt": "N/A",
                "status": "PAGE_ERROR",
                "http_code": "N/A",
                "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return results


def save_to_csv(all_results, filename, write_header=True):
    """Saves all results to a CSV file."""
    if not all_results:
        print("No data to save to CSV.")
        return

    fieldnames = [
        "page_url",
        "image_url",
        "image_alt",
        "status",
        "http_code",
        "scan_date",
    ]

    mode = "w" if write_header else "a"
    with open(filename, mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(all_results)

    if write_header:
        print(f"📄 Report created: {filename}")

def append_to_csv(results, filename):
    """Appends new results to existing CSV file."""
    if results:
        save_to_csv(results, filename, write_header=False)


def main():
    """Main execution logic."""
    print(f"Getting URLs from sitemap: {SITEMAP_URL}")
    all_page_urls = get_urls_from_sitemap(SITEMAP_URL)

    if not all_page_urls:
        print("No URLs found. Check the sitemap URL.")
        return

    print(f"Found {len(all_page_urls)} URLs to scan.\n")
    
    # Timestamp generation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"image_report_{timestamp}.csv"
    
    # Create CSV file with headers
    save_to_csv([], csv_filename, write_header=True)
    
    all_results = []
    total_broken = 0
    processed_pages = 0

    for url in all_page_urls:
        processed_pages += 1
        print(f"🔎 Scanning page {processed_pages}/{len(all_page_urls)}: {url}")
        
        page_results = check_images_on_page(url)
        all_results.extend(page_results)
        
        append_to_csv(page_results, csv_filename)
        
        broken_count = len([r for r in page_results if r["status"] == "BROKEN"])
        total_broken += broken_count
        
        print(f"   -> Progress: {processed_pages}/{len(all_page_urls)} pages completed")

    print("\n--- Scan Completed ---")
    print(f"Total images analyzed: {len(all_results)}")
    if total_broken == 0:
        print("No broken images found.")
    else:
        print(f"Found {total_broken} broken images.")
    print(f"Final report saved to: {csv_filename}")


if __name__ == "__main__":
    main()
