#!/usr/bin/python3
# Copyright 2023 Benjamin Steenkamer
from concurrent.futures import ThreadPoolExecutor
import os
import re
import shutil
import urllib.request
import urllib.error
import http.client

HF = "https://www.harborfreight.com/coupons"
HF_PROMO = "https://www.harborfreight.com/promotions"   # percent off coupons
HFQPDB = "https://www.hfqpdb.com"
SAVE_DIR = "upload_to_hfqpdb/"

failure_urls = []

def dl_and_hash_coupon(url):
    print("Downloading:", url)
    last_slash = url.rfind("/") + 1
    image_name =  url[last_slash:]
    try:
        image_bytes = urllib.request.urlopen(url).read()
        return image_bytes, hash(image_bytes), image_name
    except (urllib.error.URLError, http.client.InvalidURL):
        # URLError = image doesn't actually exist on HF website
        # InvalidURL = bugged file path on HF website
        failure_urls.append(url)
        return None, None, image_name

hfqpdb_requests= []  # Store pending/complete web request
hf_requests = []

# Do coupon downloading on many threads
# TODO coupons are sometimes hidden on mobile coupon site: https://go.harborfreight.com/coupons/
with ThreadPoolExecutor() as executor:
    # Get current database coupons
    with urllib.request.urlopen(f"{HFQPDB}/browse") as hfqpdb_page:
        for line in hfqpdb_page.readlines():
            p = re.search("\/coupons\/(.+?)(png|jpg)", line.decode())
            if p is not None:
                p = p.group().replace("/coupons/thumbs/tn_", f"{HFQPDB}/coupons/")    # Replace thumbnail image with full resolution image
                hfqpdb_requests.append(executor.submit(dl_and_hash_coupon, p))
    # Get HF coupons from main coupon page
    with urllib.request.urlopen(HF) as hf_page:
        for line in hf_page.readlines():
            p = re.search("https:\/\/images\.harborfreight\.com\/hftweb\/weblanding\/coupon-deals\/images\/(.+?)png", line.decode())
            if p is not None:
                p = p.group()
                hf_requests.append(executor.submit(dl_and_hash_coupon, p))

    # Get HF promo coupons (% off entire store, etc.)
    with urllib.request.urlopen(HF_PROMO) as hf_page:
        for line in hf_page.readlines():
            p = re.search("https:\/\/images\.harborfreight\.com\/hftweb\/promotions(.+?)png", line.decode())
            if p is not None:
                p = p.group()
                hf_requests.append(executor.submit(dl_and_hash_coupon, p))

if os.path.exists(SAVE_DIR):
    shutil.rmtree(SAVE_DIR) # Delete old coupon folder, if it exists

hfqpdb_images_hashes = []
for r in hfqpdb_requests:
    if r.result()[1] is not None:
        hfqpdb_images_hashes.append(r.result()[1])   # Only care about hash of DB images

# Print out image URLs that failed to downloaded
if len(failure_urls) > 0:
    print("\nFAILED TO DOWNLOAD:")
    for url in failure_urls:
        print(url)

# Save images that weren't found on HFQPDB
not_found = []
for r in hf_requests:
    image, image_hash, name = r.result()
    if image_hash is not None and image_hash not in hfqpdb_images_hashes:
        os.makedirs(SAVE_DIR, exist_ok=True)
        not_found.append(name)
        with open(f"{SAVE_DIR}{name}", "wb") as fp:
            fp.write(image)

# Print out image names that were not found on HFQPDB
if len(not_found) != 0:
    print("\nNot found in database:")
    for name in not_found:
        print(name)

print(f"\n{len(hf_requests) - len(not_found)}/{len(hf_requests)} Harbor Freight coupons found on HFQPDB (DB coupon count={len(hfqpdb_images_hashes)})")
# Expect the DB size to be larger than the current HF coupon page; DB contains never expire coupons that HF doesn't advertise

if len(not_found) == 0:
    print("HFQPDB IS UP TO DATE")
else:
    print(f"Consider uploading the {len(not_found)} missing coupon(s) in to {HFQPDB}/mass_coupon_submit\nCoupon save location: {os.getcwd()}{os.sep}{SAVE_DIR}")
input("Press ENTER key to exit")
