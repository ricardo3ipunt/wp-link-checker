import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
import csv
import argparse
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="WordPress Image Link Checker - Scans a WordPress site for broken images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python wp-link-checker.py example.com
  python wp-link-checker.py my-blog.wordpress.com
        """
    )
    
    parser.add_argument(
        "domain",
        help="WordPress domain to scan (e.g., example.com)"
    )
    
    parser.add_argument(
        "--protocol",
        choices=["http", "https"],
        default="https",
        help="Protocol to use (default: https)"
    )
    
    return parser.parse_args()


def get_urls_from_sitemap(sitemap_url):
    """Gets all page URLs from a WordPress sitemap, focusing only on posts/articles."""
    urls = []
    try:
        r = requests.get(sitemap_url, timeout=10, verify=False)
        r.raise_for_status()
        sp = BeautifulSoup(r.text, "xml")

        # Check if it's a sitemap index
        sitemap_elements = sp.find_all("sitemap")

        if sitemap_elements:
            # Filter nested sitemaps to only include posts and pages (not categories, tags, users)
            for sitemap in sitemap_elements:
                loc_tag = sitemap.find("loc")
                if loc_tag:
                    nested_sitemap_url = loc_tag.text
                    
                    # WordPress sitemap patterns to include (posts and articles)
                    include_patterns = [
                        'wp-sitemap-posts-post-',      # Blog posts/articles
                        'wp-sitemap-posts-page-',      # Static pages (optional, might contain articles)
                        'sitemap-posts-',
                        'sitemap_index.xml',
                    ]
                    
                    # WordPress sitemap patterns to exclude (taxonomies, users, etc.)
                    exclude_patterns = [
                        'wp-sitemap-taxonomies-category-',
                        'wp-sitemap-taxonomies-post_tag-',
                        'wp-sitemap-taxonomies-',
                        'wp-sitemap-users-',
                        'sitemap-categories-',
                        'sitemap-tags-',
                        'sitemap-authors-',
                    ]
                    
                    # Check if this sitemap should be included
                    should_include = any(pattern in nested_sitemap_url for pattern in include_patterns)
                    should_exclude = any(pattern in nested_sitemap_url for pattern in exclude_patterns)
                    
                    if should_include and not should_exclude:
                        print(f"   -> Processing sitemap: {nested_sitemap_url}")
                        urls.extend(get_urls_from_sitemap(nested_sitemap_url))
                    elif should_exclude:
                        print(f"   -> Skipping taxonomy/user sitemap: {nested_sitemap_url}")
                    else:
                        # If uncertain, process it but warn
                        print(f"   -> Processing unknown sitemap type: {nested_sitemap_url}")
                        urls.extend(get_urls_from_sitemap(nested_sitemap_url))
        else:
            # It's a regular sitemap, get all URL locations
            url_locs = sp.find_all("loc")
            urls = [url.text for url in url_locs]
            print(f"   -> Found {len(urls)} URLs in this sitemap")

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
            return "OK", status_code
        elif status_code == 301:
            return "PROBABLY_OK", status_code
        else:
            return "BROKEN", status_code

    except requests.RequestException:
        return "BROKEN", "Connection failed"


def check_images_on_page(page_url):
    """Finds and checks the status of all images on a given URL, focusing on main content area."""
    results = []

    try:
        response = requests.get(page_url, timeout=10, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        
        # WordPress main content selectors (ordered by priority)
        content_selectors = [
            '#primary',                    # Most common WordPress primary content area
            '.primary',                    # Class-based primary selector
            '#content',                    # Alternative content ID
            '.content-area',              # Common WordPress theme class
            '.entry-content',             # Post content area
            '.post-content',              # Alternative post content
            '.article-content',           # Some themes use article-content
            'main',                       # HTML5 semantic main element
            '.main-content',              # Generic main content class
            '#main',                      # Main ID selector
            '.site-content',              # WordPress site content wrapper
            '.hentry',                    # WordPress post entry class
            'article',                    # HTML5 semantic article element
            '.post',                      # Generic post class
            '.content'                    # Generic content class
        ]
        
        # Try to find the main content area
        content_area = None
        used_selector = None
        
        for selector in content_selectors:
            content_area = soup.select_one(selector)
            if content_area:
                used_selector = selector
                break
        
        if content_area is None:
            print("   -> ⚠️  No main content area found, scanning entire page")
            content_area = soup.find('body') or soup
            used_selector = 'body (fallback)'
        else:
            print(f"   -> Found main content using selector: {used_selector}")
        
        # Find images within the content area
        img_tags = content_area.find_all("img")
        print(f"   -> Found {len(img_tags)} images in main content area")

        for img_tag in img_tags:
            img_src = img_tag.get("src")
            if not img_src:
                continue

            img_url = urljoin(page_url, img_src)
            img_alt = img_tag.get("alt", "")

            status, http_code = check_image_status(img_url)

            # Only report images that need attention
            if status in ["BROKEN", "PROBABLY_OK"]:
                emoji = "❌" if status == "BROKEN" else "⚠️"
                action = "Broken" if status == "BROKEN" else "Needs Manual Check"
                print(f"   -> {emoji} {action}: {img_url} (Code: {http_code})")

                results.append(
                    {
                        "page_url": page_url,
                        "image_url": img_url,
                        "image_alt": img_alt,
                        "status": status,
                        "http_code": str(http_code),
                        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "content_selector": used_selector,
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
                "content_selector": "N/A",
            }
        )

    return results


def save_to_csv(all_results, filename, write_header=True):
    """Saves results to a CSV file."""
    fieldnames = [
        "page_url",
        "image_url",
        "image_alt",
        "status",
        "http_code",
        "content_selector",
        "scan_date",
    ]

    mode = "w" if write_header else "a"
    with open(filename, mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
            print(f"Report created: {filename}")

        if all_results:
            writer.writerows(all_results)


def append_to_csv(results, filename):
    """Appends new results to existing CSV file."""
    if results:
        save_to_csv(results, filename, write_header=False)


def main():
    """Main execution logic."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set up configuration from arguments
    wp_domain = args.domain
    wp_url = f"{args.protocol}://{wp_domain}"
    sitemap_url = f"{wp_url}/wp-sitemap.xml"
    
    print(f"Scanning domain: {wp_domain}")
    print(f"Getting URLs from sitemap: {sitemap_url}")
    
    all_page_urls = get_urls_from_sitemap(sitemap_url)

    if not all_page_urls:
        print("No URLs found. Check the sitemap URL.")
        return

    print(f"Found {len(all_page_urls)} URLs to scan.\n")

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"{wp_domain}_image_report_{timestamp}.csv"

    # Create CSV file with headers
    save_to_csv([], csv_filename, write_header=True)

    all_results = []
    total_broken = 0
    total_probably_ok = 0

    for i, url in enumerate(all_page_urls, 1):
        print(f"🔎 Scanning page {i}/{len(all_page_urls)}: {url}")

        page_results = check_images_on_page(url)
        all_results.extend(page_results)

        # Save results incrementally
        append_to_csv(page_results, csv_filename)

        # Count issues
        broken_count = len([r for r in page_results if r["status"] == "BROKEN"])
        probably_ok_count = len(
            [r for r in page_results if r["status"] == "PROBABLY_OK"]
        )

        total_broken += broken_count
        total_probably_ok += probably_ok_count

        print(f"   -> Progress: {i}/{len(all_page_urls)} pages completed\n")

    # Final summary
    print("--- Scan Completed ---")
    print(f"Total images analyzed: {len(all_results)}")
    print(f"Broken images: {total_broken}")
    print(f"Images needing manual check: {total_probably_ok}")

    if total_broken == 0 and total_probably_ok == 0:
        print("No issues found!")
    else:
        print(f"Detailed report saved to: {csv_filename}")


if __name__ == "__main__":
    main()
