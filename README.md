# Is it on HFQPDB?
This script checks if the currently active Harbor Freight coupons have been uploaded to the Harbor Freight Tools Coupon Database.  
It downloads all the coupons from https://www.harborfreight.com/coupons and https://www.hfqpdb.com/browse then compares the two sets. 
If a coupon is not present on the "browse" page of the database, the coupon image is saved to `upload_to_hfqdb/` for you to manually upload.

Copyright 2023 Benjamin Steenkamer
