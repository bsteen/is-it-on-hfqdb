#!/usr/bin/python3
# Copyright 2023 Benjamin Steenkamer
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import http.client
import numpy as np
import os
import re
import shutil
import urllib.error
import urllib.request
import cv2
from tqdm import tqdm


HF = "https://www.harborfreight.com/coupons"
HF_PROMO = "https://www.harborfreight.com/promotions"   # percent off coupons
HFQPDB = "https://www.hfqpdb.com"
SAVE_DIR = "upload/"
SIMILAR_THRESHOLD = 0.9     # How similar two images have to be to be considered the same


def download_coupons(url, re_search, desc, npos, replace="", replace_with=""):
    failed_urls = []
    coupon_urls = []
    try:
        with urllib.request.urlopen(url) as web_page:
            for line in web_page.readlines():
                coupon_url = re.search(re_search, line.decode())
                if coupon_url is not None:
                    coupon_urls.append(coupon_url.group().replace(replace, replace_with))
    except urllib.error.URLError:
        failed_urls.append(url)

    def _thread(url):
        last_slash = url.rfind("/") + 1
        image_name = url[last_slash:]
        try:
            image_bytes = urllib.request.urlopen(url).read()
            return image_bytes, hash(image_bytes), image_name, url
        except (urllib.error.URLError, http.client.InvalidURL):
            # URLError = image doesn't actually exist on HF website
            # InvalidURL = bugged file path on HF website
            return None, None, image_name, url

    requests = []
    with ThreadPoolExecutor() as tpool:
        for url in coupon_urls:
            requests.append(tpool.submit(_thread, url))

    coupons = []
    if requests:
        pbar = tqdm(total=len(requests), ncols=100, position=npos, desc=desc)
        for request in as_completed(requests):  # yields futures as they complete
                result = request.result()
                if result[0] is not None:
                    coupons.append(result[:-1])
                else:
                    failed_urls.append(result[-1])
                pbar.update(1)
    elif not failed_urls:   # Only prints if no failed URLs and no coupon downloaded
        print("No coupons found    :", url)

    return coupons, failed_urls


def coupons_are_similar(coupon_a, coupon_b):
    def template_cmp(image, template_image):
        """
        Slides template_image over image, checking for similarities; template_image must not be greater than the image dimensions
        """
        try:
            res = cv2.matchTemplate(image, template_image, cv2.TM_CCOEFF_NORMED)
            if np.where(res >= SIMILAR_THRESHOLD)[0].size > 0:   # If there are similarities greater than threshold, they are probably the same coupon
                return True
            return False
        except cv2.error:   # Happens when the template is larger than input image
            return None

    nparr_a = np.frombuffer(coupon_a, np.uint8) # Convert binary string to ndarray
    nparr_b = np.frombuffer(coupon_b, np.uint8)

    img_a = cv2.imdecode(nparr_a, cv2.IMREAD_COLOR)  # Convert ndarray to CV2 image
    img_b = cv2.imdecode(nparr_b, cv2.IMREAD_COLOR)

    coupon_a_gray = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY) # Convert to grayscale
    coupon_b_gray = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)

    # Try to use coupon A as input, coupon b as the template
    # If that fails, switch the two around and try again
    are_similar = template_cmp(coupon_a_gray, coupon_b_gray)
    if are_similar is None:
         are_similar = template_cmp(coupon_b_gray, coupon_a_gray)

    return are_similar if are_similar is not None else False


def process_coupon(hf_coupon, database):
    not_found = None
    hf_image, hf_image_hash, hf_name = hf_coupon

    if hf_image_hash is not None:
        save = True
        for db_image, db_image_hash, _db_name in database:
            if hf_image_hash == db_image_hash or coupons_are_similar(db_image, hf_image): # Coupon images are exactly the same (hash) or are fairly similar (CV template match)
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

    # Delete old coupon folder, if it exists
    if os.path.exists(SAVE_DIR):
        shutil.rmtree(SAVE_DIR)

    p_executor = ProcessPoolExecutor()
    db_requests = p_executor.submit(download_coupons, *(f"{HFQPDB}/browse", "\/coupons\/(.+?)(png|jpg)", "Downloading HFQPDB  ", 0, "/coupons/thumbs/tn_", f"{HFQPDB}/coupons/"))
    main_requests= p_executor.submit(download_coupons, *(HF, "https:\/\/images\.harborfreight\.com\/hftweb\/weblanding\/coupon-deals\/images\/(.+?)png", "Downloading HF      ", 1))
    promo_request = p_executor.submit(download_coupons, *(HF_PROMO, "https:\/\/images\.harborfreight\.com\/hftweb\/promotions(.+?)png", "Downloading HF Promo", 2))

    # Gather downloaded coupons
    db_coupons = db_requests.result()[0]
    hf_coupons = main_requests.result()[0] + promo_request.result()[0]
    failed_urls = db_requests.result()[1] + main_requests.result()[1] + promo_request.result()[1]

    process_reqs = []
    for hf_coupon in hf_coupons:
        process_reqs.append(p_executor.submit(process_coupon, hf_coupon, db_coupons))

    not_found = []
    for process_coupon_request in tqdm(process_reqs, desc="Processing coupons  ", ncols=100):
        coupon_not_found = process_coupon_request.result()
        if coupon_not_found is not None:
            not_found.append(coupon_not_found)

    # Print out image URLs that failed to download; all web request are completed at this point
    if failed_urls:
        print("\nFAILED TO DOWNLOAD:")
        for url in failed_urls:
            print(url)

    # Print out image names that were not found on HFQPDB
    if len(not_found) != 0:
        print("\nNot found on HFQPDB:")
        for name in not_found:
            print(name)

    # Expect the DB size to be larger than the current HF coupon page; DB contains never expire coupons that HF doesn't advertise
    print(f"\n{len(hf_coupons) - len(not_found)}/{len(hf_coupons)} Harbor Freight coupons found on HFQPDB (DB coupon count={len(db_coupons)})")

    if len(not_found) == 0:
        print("HFQPDB IS UP TO DATE")
    else:
        print(f"Consider uploading the {len(not_found)} missing coupon(s) in to {HFQPDB}/mass_coupon_submit\nCoupon save location: {os.getcwd()}{os.sep}{SAVE_DIR}")
    input("Press ENTER key to exit")
