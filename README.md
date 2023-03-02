# Is it on HFQPDB?
This script checks if Harbor Freight coupons (https://www.harborfreight.com/coupons)
have been posted to the coupon database (https://www.hfqpdb.com).  
It downloads all the **active** coupons from HF and the database then compares the two sets to see if any of the HF coupons are not in the **active** coupons database.  
If a HF coupon is not present on the database, the image is saved to `upload_to_hfqdb/` for manual upload.

Copyright 2023 Benjamin Steenkamer
