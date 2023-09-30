#!/usr/bin/python3
# Copyright 2023 Benjamin Steenkamer
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import cv2
import http.client
import numpy as np
import os
import re
import shutil
import urllib.error
import urllib.request

HF = "https://www.harborfreight.com/coupons"
HF_PROMO = "https://www.harborfreight.com/promotions"   # percent off coupons
HFQPDB = "https://www.hfqpdb.com"
SAVE_DIR = "upload/"
SIMILAR_THRESHOLD = 0.9     # How similar two images have to be to be considered the same


failure_urls = []    # Image URLs that failed to download
hfqpdb_requests= []  # Store pending/complete web request
hf_requests = []


def dl_and_hash_coupon(url):
    print("Downloading:", url)
    last_slash = url.rfind("/") + 1
    image_name = url[last_slash:]
    try:
        image_bytes = urllib.request.urlopen(url).read()
        return image_bytes, hash(image_bytes), image_name
    except (urllib.error.URLError, http.client.InvalidURL):
        # URLError = image doesn't actually exist on HF website
        # InvalidURL = bugged file path on HF website
        failure_urls.append(url)
        return None, None, image_name


def coupons_are_similar(coupon_a, coupon_b):
    nparr_a = np.frombuffer(coupon_a, np.uint8) # Convert binary string to ndarray
    nparr_b = np.frombuffer(coupon_b, np.uint8)

    img_np_a = cv2.imdecode(nparr_a, cv2.IMREAD_COLOR)  # Convert to image
    img_np_b = cv2.imdecode(nparr_b, cv2.IMREAD_COLOR)

    coupon_a_gray = cv2.cvtColor(np.asarray(img_np_a), cv2.COLOR_BGR2GRAY)      # Convert to grayscale
    coupon_b_gray = cv2.cvtColor(np.asarray(img_np_b), cv2.COLOR_BGR2GRAY)

    res = cv2.matchTemplate(coupon_a_gray, coupon_b_gray, cv2.TM_CCOEFF_NORMED) # See if images match
    if np.where(res >= SIMILAR_THRESHOLD)[0].size > 0:
        return True
    return False

def process_coupon(hf_coupon, database):
    not_found = None
    hf_image, hf_image_hash, hf_name = hf_coupon

    if hf_image_hash is not None:
        save = True
        for db_image, db_image_hash, _db_name in database:
            if hf_image_hash == db_image_hash or coupons_are_similar(hf_image, db_image): # Coupon images are exactly the same (hash) or are fairly similar (CV template match)
                save = False
                break
        if save:
            os.makedirs(SAVE_DIR, exist_ok=True)
            not_found = hf_name
            with open(f"{SAVE_DIR}{hf_name}", "wb") as fp:
                fp.write(hf_image)

    return not_found

if __name__ == "__main__":
    # Do coupon downloading on many threads
    # TODO coupons are sometimes hidden on mobile coupon site: https://go.harborfreight.com/coupons/
    with ThreadPoolExecutor() as t_executor:
        # Get current database coupons
        with urllib.request.urlopen(f"{HFQPDB}/browse") as hfqpdb_page:
            for line in hfqpdb_page.readlines():
                p = re.search("\/coupons\/(.+?)(png|jpg)", line.decode())
                if p is not None:
                    p = p.group().replace("/coupons/thumbs/tn_", f"{HFQPDB}/coupons/")    # Replace thumbnail image with full resolution image
                    hfqpdb_requests.append(t_executor.submit(dl_and_hash_coupon, p))
        # Get HF coupons from main coupon page
        with urllib.request.urlopen(HF) as hf_page:
            for line in hf_page.readlines():
                p = re.search("https:\/\/images\.harborfreight\.com\/hftweb\/weblanding\/coupon-deals\/images\/(.+?)png", line.decode())
                if p is not None:
                    p = p.group()
                    hf_requests.append(t_executor.submit(dl_and_hash_coupon, p))

        # Get HF promo coupons (% off entire store, etc.)
        with urllib.request.urlopen(HF_PROMO) as hf_page:
            for line in hf_page.readlines():
                p = re.search("https:\/\/images\.harborfreight\.com\/hftweb\/promotions(.+?)png", line.decode())
                if p is not None:
                    p = p.group()
                    hf_requests.append(t_executor.submit(dl_and_hash_coupon, p))

    # Delete old coupon folder, if it exists
    if os.path.exists(SAVE_DIR):
        shutil.rmtree(SAVE_DIR)

    # Gather DB coupon results
    hfqpdb_coupons = []
    for r in hfqpdb_requests:
        if r.result()[1] is not None:           # Must wait for entire DB to be retrieved before proceeding
            hfqpdb_coupons.append(r.result())

    # Gather HF coupon web requests and distribute to parallel processes
    hf_coupon_count = len(hf_requests)
    processes = []
    with ProcessPoolExecutor() as p_executor:
        while hf_requests:                  # Loop through web requests, skip requests that haven't completed yet
            request = hf_requests.pop(0)
            try:
                result = request.result(0.001)
                processes.append(p_executor.submit(process_coupon, result, hfqpdb_coupons))   # Save images that weren't found on HFQPDB
            except TimeoutError:
                hf_requests.append(request)

    not_found = []
    for process in processes:
        coupon_not_found = process.result()
        if coupon_not_found is not None:
            not_found.append(coupon_not_found)

    # Print out image URLs that failed to download; all web request are completed at this point
    if len(failure_urls) > 0:
        print("\nFAILED TO DOWNLOAD:")
        for url in failure_urls:
            print(url)

    # Print out image names that were not found on HFQPDB
    if len(not_found) != 0:
        print("\nNot found on HFQPDB:")
        for name in not_found:
            print(name)

    # Expect the DB size to be larger than the current HF coupon page; DB contains never expire coupons that HF doesn't advertise
    print(f"\n{hf_coupon_count - len(not_found)}/{hf_coupon_count} Harbor Freight coupons found on HFQPDB (DB coupon count={len(hfqpdb_coupons)})")

    if len(not_found) == 0:
        print("HFQPDB IS UP TO DATE")
    else:
        print(f"Consider uploading the {len(not_found)} missing coupon(s) in to {HFQPDB}/mass_coupon_submit\nCoupon save location: {os.getcwd()}{os.sep}{SAVE_DIR}")
    input("Press ENTER key to exit")
