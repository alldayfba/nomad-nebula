# PART 1: COMPLETE KEEPA API DOCUMENTATION

## 1.1 API Plans & Token System

**Token Bucket Algorithm:** Tokens generated per minute, unused tokens expire after 60 minutes.

| Plan | Tokens/Min | Bucket Capacity (60min) | Monthly Max Products (31d) | Price |
|------|-----------|------------------------|---------------------------|-------|
| Basic | 5 | 300 | ~223,200 | ~€10/mo |
| Mid | 20 | 1,200 | ~892,800 | ~€20/mo |
| Pro | 60 | 3,600 | ~2,678,400 | ~€60/mo |

- Multiple subscriptions stack (same API key, additive tokens)
- Upgrade anytime, downgrade once per 28 days (prorated)
- Payment via Stripe only, no discounts

### How to Make Requests
- **Base URL:** `https://api.keepa.com/`
- **Method:** HTTPS GET (gzip encoding required), some endpoints accept POST
- **Auth:** `key=<yourAccessKey>` parameter
- **Parallel:** Supported, Keep-Alive recommended
- **Response format:** JSON with token metadata

**Response always includes:**
```json
{
  "refillRate": <tokens/min>,
  "tokensLeft": <current balance, can go negative>,
  "tokensConsumed": <this request>,
  "processingTimeInMs": <server time>,
  "error": <only if error>
}
```

**HTTP Status Codes:**
| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Malformed request |
| 402 | Payment required / access denied |
| 405 | Parameter out of range |
| 429 | Token depletion (rate limited) |
| 500 | Server error |

**Keepa Time:** Minutes since custom epoch. Convert: `(keepaTime + 21564000) * 60` = Unix seconds

---

## 1.2 Available Requests (All Endpoints)

### A. Request Products (`/product`)
**Token Cost:** 1 per ASIN (base)

```
GET /product?key=<key>&domain=<domainId>&asin=<ASIN1,ASIN2,...>
GET /product?key=<key>&domain=<domainId>&code=<UPC/EAN/ISBN>
```

- Batch up to **100 ASINs** per request (comma-separated)
- `code` accepts UPC, EAN, ISBN-13 (cannot use both `asin` and `code`)
- Auto-refreshes if data >1 hour old

**Optional Parameters & Extra Token Costs:**

| Parameter | Extra Cost | Description |
|-----------|-----------|-------------|
| `stats=<days>` | 0 | Current prices, min/max, weighted means. Accepts days (e.g., 180) or date range |
| `history=0` | 0 | Exclude CSV and historical fields (saves bandwidth) |
| `days=<N>` | 0 | Limit history to recent N days |
| `offers=<N>` | 6 per offer page (10 offers/page) | Marketplace offers, up to 100. Response time 2-20s |
| `only-live-offers=1` | 0 | Only active offers (requires `offers`) |
| `rating=1` | up to 1 | Rating/review count history |
| `buybox=1` | 2 | Current + historical Buy Box data |
| `stock=1` | 2 (conditional) | Stock data in offers; 2 tokens only if updated within 7 days |
| `videos=1` | 0 | Video metadata |
| `aplus=1` | 0 | A+ content |
| `historical-variations=1` | 1 | Historical and OOS variations |
| `update=<hours>` | 0-1 | Force refresh if older than N hours; 0 = always refresh (+1 token) |
| `code-limit=<N>` | 0 | Max products per product code |

**Not available for:** digital products, movie rentals, bundles, Amazon Fresh, luxury stores, Amazon Haul/Bazaar

---

### B. Product Searches (`/search`)
**Token Cost:** 10 per result page (up to 10 results per page)

```
GET /search?key=<key>&domain=<domainId>&type=product&term=<searchTerm>
```

- Up to **100 results** per search term (10 pages × 10 results)
- Results match Amazon search order (excluding sponsored)
- Returns full product objects by default

**Optional Parameters:**
| Parameter | Description |
|-----------|-------------|
| `asins-only=1` | Return ASINs only (no product objects) |
| `page=<0-9>` | Page number; default returns first 40 results |
| `stats=<days>` | Add pricing stats (no extra cost) |
| `update=<hours>` | Force refresh (0 = +1 token per product) |
| `history=0` | Exclude CSV history |
| `rating=1` | Rating/review history (up to 1 extra token/product, max 5/search) |

---

### C. Browsing Deals (`/deal`)
**Token Cost:** 5 per 150 deals

```
GET /deal?key=<key>&selection=<URL-encoded queryJSON>
POST /deal?key=<key>  (body: queryJSON)
```

- Max **150 deals/request**, up to **10,000 via paging**
- Only products updated within last **12 hours**
- Tip: Keepa deals page has "Show API query" link to generate queryJSON

**queryJSON Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | Int | Pagination (start at 0, stop when <150 results) |
| `domainId` | Int | Amazon locale (required) |
| `priceTypes` | [Int] | Deal type — exactly ONE entry required |
| `dateRange` | Int | 0=Day, 1=Week, 2=Month, 3=3Months |

**Price Types:**
| Value | Type |
|-------|------|
| 0 | AMAZON price |
| 1 | NEW marketplace |
| 2 | USED marketplace |
| 3 | SALES rank |
| 5 | COLLECTIBLE |
| 6 | REFURBISHED |
| 7 | NEW_FBM + shipping |
| 8 | LIGHTNING_DEAL |
| 9 | WAREHOUSE |
| 10 | NEW_FBA |
| 18 | BUY_BOX + shipping |
| 19-22 | USED conditions + shipping |
| 32 | BUY_BOX_USED + shipping |
| 33 | PRIME_EXCL |

**Filter Options:**
| Filter | Type | Description |
|--------|------|-------------|
| `isFilterEnabled` | Bool | Enable filters |
| `includeCategories` | [Long] | Only these categories (up to 500 IDs) |
| `excludeCategories` | [Long] | Exclude these categories |
| `minRating` | Int | 0-50 scale (-1 = inactive) |
| `isLowest` | Bool | At all-time lowest |
| `isLowest90` | Bool | At 90-day lowest |
| `isLowestOffer` | Bool | Lowest of all New offers |
| `isHighest` | Bool | At all-time highest |
| `isOutOfStock` | Bool | Was available, now OOS |
| `isBackInStock` | Bool | Was OOS, now back |
| `hasReviews` | Bool | Must have reviews |
| `filterErotic` | Bool | Exclude adult items |
| `singleVariation` | Bool | One variation per parent |
| `isRisers` | Bool | Price rising |
| `isPrimeExclusive` | Bool | Prime Exclusive only |
| `mustHaveAmazonOffer` | Bool | Amazon must be selling |
| `mustNotHaveAmazonOffer` | Bool | Amazon must NOT be selling |
| `warehouseConditions` | [Int] | Warehouse deal conditions |
| `titleSearch` | String | Keyword search (case-insensitive, up to 50 keywords, AND logic) |
| `brand` | [String] | Brand filter |
| `manufacturer` | [String] | Manufacturer filter |
| `material`, `type`, `color`, `size`, `scent`, `itemForm`, `pattern`, `style` | [String] | Product attribute filters |
| `binding`, `author`, `edition`, `format`, `languages` | [String] | Content filters |
| `brandStoreName`, `brandStoreUrlName` | [String] | Brand store filters |
| `websiteDisplayGroup`, `salesRankDisplayGroup` | [String] | Display group filters |

**Range Options** (all `[min, max]` integer arrays):
| Range | Description |
|-------|-------------|
| `isRangeEnabled` | Enable ranges |
| `currentRange` | Current price range (in cents) |
| `deltaRange` | Weighted avg vs current difference |
| `deltaPercentRange` | Same but in % (min 10%, Sales Rank min 80%) |
| `deltaLastRange` | Previous vs current difference |
| `salesRankRange` | BSR range (-1 = no upper bound) |

**Sort Options:**
| Value | Sort By | Order |
|-------|---------|-------|
| 1 | Deal age | Newest first |
| 2 | Absolute delta | Highest first |
| 3 | Sales Rank | Lowest first |
| 4 | Percentage delta | Highest first |
| Negative | Inverted | Reversed |

**Response:** `{ "dr": [deal objects], "categoryIds": [Long], "categoryNames": [String], "categoryCount": [Int] }`

---

### D. Request Best Sellers (`/bestsellers`)
**Token Cost:** 50

```
GET /bestsellers?key=<key>&domain=<domainId>&category=<categoryId>&range=<range>
```

- Root categories: up to **500,000 ASINs**
- Sub-categories: up to **10,000 ASINs**
- Product groups / display groups: up to **100,000 ASINs**
- Updated hourly, ordered by best-selling

**Parameters:**
| Parameter | Values | Description |
|-----------|--------|-------------|
| `category` | Long | Category node ID, product group name, or display group name |
| `range` | 0/30/90/180 | Current rank or N-day average |
| `month` + `year` | 1-12, YYYY | Historical list (last 36 months, not current month) |
| `variations` | 0/1 | 0=collapse to one per parent (default), 1=all variations |
| `sublist` | 0/1 | 0=primary rank (default), 1=sub-category rank |

**Response:** `bestSellersList` → Best Sellers Object

---

### E. Category Lookup (`/category`)
**Token Cost:** 1

```
GET /category?key=<key>&domain=<domainId>&category=<categoryId>&parents=<0|1>
```

- Batch up to **10 category IDs** (comma-separated), same token cost
- `categoryId=0` → all root categories
- `parents=1` → include parent hierarchy (+0 extra tokens, included in base cost)
- Cannot provide data for promotional categories (e.g., Launchpad)

**Response:** `{ "categories": {"catId": catObj, ...}, "categoryParents": {"catId": catObj, ...} }`

---

### F. Category Searches (`/search?type=category`)
**Token Cost:** 1

```
GET /search?key=<key>&domain=<domainId>&type=category&term=<searchTerm>
```

- Up to **50 matching categories**
- Min keyword length: 3 chars
- Multiple space-separated keywords (AND logic)

---

### G. Request Seller Information (`/seller`)
**Token Cost:** 1 per seller (+9 for storefront = 10 total)

```
GET /seller?key=<key>&domain=<domainId>&seller=<sellerId1,sellerId2,...>
```

- Batch up to **100 seller IDs** (comma-separated)
- `storefront=1` → ASIN listings (up to 100,000 items), costs +9 tokens
  - Includes current + last 7 days listings
  - **Cannot batch when using storefront parameter**

**Response:** `{ "sellers": {"sellerId": sellerObj, ...} }`

---

### H. Most Rated Sellers (`/topseller`)
**Token Cost:** 50

```
GET /topseller?key=<key>&domain=<domainId>
```

- Up to **100,000 seller IDs** ordered highest-to-lowest rated
- Updated daily
- Pairs with Seller Information endpoint for details

**Response:** `{ "sellerIdList": ["A1PA6795UKMFR9", ...] }`

---

### I. Product Finder (`/finder`)
**Token Cost:** Variable (similar to deals, ~5 tokens per query)

POST-based endpoint with 20+ advanced filters for opportunity discovery:
- Category, rating range, seller count, sales volume thresholds, price range
- Brand, author, title filters
- Sales rank ranges
- Almost all product fields can be searched and sorted

*(Full filter schema mirrors Deals queryJSON structure with additional product-specific filters)*

---

### J. Lightning Deals
**Token Cost:** Referenced in deals priceType=8
- Active deals end with -1 future date in CSV
- Upcoming deals announced with -1 future start date
- Delta calculations use Amazon/New price as reference (not lightning deal history)

---

### K. Tracking Products
- Create price/availability alerts on specific ASINs
- Notification via webhook when thresholds are met
- Token cost: referenced in tracking creation objects

---

### L. Graph Image API
- Download Keepa-style PNG chart showing price history + sales rank
- Parameters: ASIN, domain, image size, price types to include
- No token cost documented (likely included in product request)

---

## 1.4 Statistics Object (FROM OFFICIAL JAVA SOURCE — `Stats.java`)

The Statistics Object is returned when `stats` parameter is used. **This is the richest data object in the entire API.**

### Price/Rank Arrays (all indexed by CsvType — 36 indices)
| Field | Type | Description |
|-------|------|-------------|
| `current[]` | int[] | Current prices/ranks at last update (-1 = OOS) |
| `avg[]` | int[] | Weighted mean for requested interval |
| `avg30[]` | int[] | 30-day weighted mean |
| `avg90[]` | int[] | 90-day weighted mean |
| `avg180[]` | int[] | 180-day weighted mean |
| `avg365[]` | int[] | 365-day weighted mean |
| `atIntervalStart[]` | int[] | Price at interval start |
| `min[][]` | int[][] | All-time min [timestamp, value] |
| `max[][]` | int[][] | All-time max [timestamp, value] |
| `minInInterval[][]` | int[][] | Interval min [timestamp, value] |
| `maxInInterval[][]` | int[][] | Interval max [timestamp, value] |
| `isLowest[]` | bool[] | Is at all-time lowest? |
| `isLowest90[]` | bool[] | Is at 90-day lowest? |

### Out-of-Stock Metrics
| Field | Type | Description |
|-------|------|-------------|
| `outOfStockCountAmazon30` | int | Amazon stockout count in 30 days |
| `outOfStockCountAmazon90` | int | Amazon stockout count in 90 days |
| `outOfStockPercentage30[]` | int[] | OOS % by price type (30d) |
| `outOfStockPercentage90[]` | int[] | OOS % by price type (90d) |
| `outOfStockPercentageInInterval[]` | int[] | OOS % in requested interval |

### Sales Velocity (KEY FOR SOURCING)
| Field | Type | Description |
|-------|------|-------------|
| `salesRankDrops30` | int | **Rank improvements in 30 days = estimated sales events** |
| `salesRankDrops90` | int | Rank improvements in 90 days |
| `salesRankDrops180` | int | Rank improvements in 180 days |
| `salesRankDrops365` | int | Rank improvements in 365 days |
| `deltaPercent90_monthlySold` | short | % change in monthlySold vs 90-day avg |

### Buy Box Data (COMPREHENSIVE)
| Field | Type | Description |
|-------|------|-------------|
| `buyBoxPrice` | int | Current Buy Box price (-2 if unavailable) |
| `buyBoxShipping` | int | Buy Box shipping cost |
| `buyBoxIsUnqualified` | bool | Unqualified Buy Box? |
| `buyBoxIsShippable` | bool | Shippable? |
| `buyBoxIsPreorder` | bool | Pre-order? |
| `buyBoxIsFBA` | bool | **FBA fulfilled?** |
| `buyBoxIsUsed` | bool | Used product in Buy Box? |
| `buyBoxIsBackorder` | bool | Backorder? |
| `buyBoxIsAmazon` | bool | **Amazon is the seller?** |
| `buyBoxIsMAP` | bool | Minimum Advertised Price? |
| `buyBoxIsPrimeExclusive` | bool | Prime exclusive? |
| `buyBoxIsFreeShippingEligible` | bool | Free shipping eligible? |
| `buyBoxIsPrimeEligible` | bool | Prime eligible? |
| `buyBoxIsPrimePantry` | bool | Prime Pantry? |
| `buyBoxMinOrderQuantity` | int | Min order qty (-1=unavailable, 0=unlimited) |
| `buyBoxMaxOrderQuantity` | int | Max order qty |
| `buyBoxAvailabilityMessage` | String | Availability text |
| `buyBoxSellerId` | String | **Current Buy Box winner seller ID** |
| `buyBoxShippingCountry` | String | Shipping country (e.g., "US") |
| `buyBoxSavingBasis` | int | Strikethrough/typical price |
| `buyBoxSavingBasisType` | String | "LIST_PRICE" or "WAS_PRICE" |
| `buyBoxSavingPercentage` | int | Discount percentage shown |
| `lastBuyBoxUpdate` | int | Last update timestamp |

### Buy Box Used
| Field | Type | Description |
|-------|------|-------------|
| `buyBoxUsedPrice` | int | Used Buy Box price |
| `buyBoxUsedShipping` | int | Used Buy Box shipping |
| `buyBoxUsedSellerId` | String | Used Buy Box seller |
| `buyBoxUsedIsFBA` | bool | Used Buy Box is FBA? |
| `buyBoxUsedCondition` | byte | 2=Like New, 3=Very Good, 4=Good, 5=Acceptable |

### Buy Box Statistics Per Seller (GAME CHANGER)
| Field | Type | Description |
|-------|------|-------------|
| `buyBoxStats` | Map<String, BuyBoxStatsObject> | **Per-seller Buy Box stats** |
| `buyBoxUsedStats` | Map<String, BuyBoxStatsObject> | Per-seller Used Buy Box stats |

**BuyBoxStatsObject:**
| Field | Type | Description |
|-------|------|-------------|
| `percentageWon` | float | **% of time this seller won Buy Box** |
| `avgPrice` | int | Average price when winning |
| `avgNewOfferCount` | int | Avg competing offers when winning |
| `isFBA` | bool | FBA fulfilled? |
| `lastSeen` | int | Last time seen winning |

### Stock & Offer Counts
| Field | Type | Description |
|-------|------|-------------|
| `totalOfferCount` | int | Total offers all conditions |
| `retrievedOfferCount` | int | Offers actually retrieved |
| `lastOffersUpdate` | int | Last offers refresh |
| `stockAmazon` | int | Amazon stock (max 10, -2=unavailable) |
| `stockBuyBox` | int | Buy Box stock level |
| `offerCountFBA` | int | FBA offer count |
| `offerCountFBM` | int | FBM offer count |
| `sellerIdsLowestFBA[]` | String[] | Sellers with lowest FBA price |
| `sellerIdsLowestFBM[]` | String[] | Sellers with lowest FBM price |
| `stockPerCondition3rdFBA[]` | int[] | Stock by condition (FBA) |
| `stockPerConditionFBM[]` | int[] | Stock by condition (FBM) |
| `isAddonItem` | bool | Add-on item flag |

### Lightning Deals
| Field | Type | Description |
|-------|------|-------------|
| `lightningDealInfo` | int[] | [startDate, endDate] in Keepa Time (null if none) |

---

## 1.5 FBA Fees Object (FROM OFFICIAL JAVA SOURCE)

```java
public class FBAFeesObject {
    int storageFee;        // Monthly storage fee (cents)
    int storageFeeTax;     // Storage fee tax
    int pickAndPackFee;    // Pick & pack fee (cents)
    int pickAndPackFeeTax; // Pick & pack fee tax
}
```

**This includes storage fees and taxes — not just pick & pack!**

---

## 1.6 Seller Object Additional Fields (FROM JAVA SOURCE)

| Field | Type | Description |
|-------|------|-------------|
| `shipsFromChina` | bool | **Seller ships from China (dropshipper signal)** |
| `currentRating` | int | Current rating percentage |
| `currentRatingCount` | int | Total current ratings |
| `ratingsLast30Days` | int | Recent rating count |
| `totalStorefrontAsinsCSV` | int[] | Historical listing count over time |

---

## 1.3 Response JSON Objects

### Product Object (COMPREHENSIVE)

**Product Types:**
| Value | Type | Notes |
|-------|------|-------|
| 0 | STANDARD | Full data access |
| 1 | DOWNLOADABLE | No marketplace offers |
| 2 | EBOOK | No marketplace offers |
| 3 | INACCESSIBLE | Limited data |
| 4 | INVALID | No current data |
| 5 | VARIATION_PARENT | Has variations set |

**Core Fields:**
- `asin`, `domainId`, `title`, `trackingSince`, `listedSince`, `lastUpdate`, `lastRatingUpdate`, `lastPriceChange`, `lastEbayUpdate`, `lastStockUpdate`

**Images/Media:** `images[]` (with l/m resolution + dimensions), `videos[]` (title, duration, creator types), `aPlus[]` (A+ content modules)

**Categories:** `rootCategory`, `categories[]`, `categoryTree[]`, `websiteDisplayGroup`, `salesRankDisplayGroup`

**Hierarchy:** `parentAsin`, `parentAsinHistory`, `variations[]` (up to 4000), `historicalVariations[]`, `frequentlyBoughtTogether[]`, `bundleItems[]`

**Identifiers:** `eanList[]`, `upcList[]`, `gtinList[]`, `partNumber`

**Brand:** `manufacturer`, `brand`, `brandStoreName`, `brandStoreUrl`, `brandStoreUrlName`

**Attributes:** `type`, `binding`, `color`, `size`, `style`, `pattern`, `edition`, `format`, `model`, `scent`, `materials[]`, `features[]` (up to 5 bullets)

**Content:** `shortDescription`, `description` (max 4000 chars, requires offers param), `activeIngredients`, `ingredients`, `itemForm`, `recommendedUsesForProduct`, `safetyWarning`, `productBenefit`

**Physical:** `packageHeight/Length/Width/Weight` (mm/grams), `itemHeight/Length/Width/Weight`, `packageQuantity`, `numberOfItems`, `numberOfPages`, `unitCount` (unitValue, unitType, eachUnitCount)

**Pricing/Fees:**
- `fbaFees` → `{ lastUpdate, pickAndPackFee }` (in cents)
- `referralFeePercentage` (Double)
- `variableClosingFee`
- `competitivePriceThreshold`, `suggestedLowerPrice`
- `businessDiscount`, `lastBusinessDiscountUpdate`

**Coupons/Promos:**
- `coupon[]` → [one-time, Subscribe & Save] (positive=absolute, negative=percentage)
- `couponHistory[]` → [keepaTime, one-time, S&S, ...] (tracked since June 2024)
- `promotions[]` → type (SNS), amount, discountPercent, snsBulkDiscountPercent
- `deals[]` → accessType, dealType (PRIME_DAY, LIMITED_TIME_DEAL, etc.), badge

**Availability:**
- `availabilityAmazon`: -1=none, 0=in stock, 1=pre-order, 2=unknown, 3=back-order, 4=delayed
- `availabilityAmazonDelay[]` → [start, end] hours
- `returnRate`: null=avg, 1=low, 2=high

**Offers/Buy Box:**
- `offers[]` → Marketplace Offer Objects (requires offers param)
- `liveOffersOrder[]` → active offer indices
- `buyBoxEligibleOfferCounts[]` → 8 elements: [New FBA, New FBM, Used FBA, Used FBM, Collectible FBA, Collectible FBM, Refurbished FBA, Refurbished FBM]
- `buyBoxSellerIdHistory[]` → [keepaTime, sellerId, ...] (-1=suppressed, -2=unidentified/OOS)
- `buyBoxUsedHistory[]` → [keepaTime, sellerId, condition, isFBA, ...]
- `offersSuccessful`, `isRedirectASIN`, `isSNS`

**Sales/Demand:**
- `monthlySold` → Amazon-provided brackets ("10+", "100+", etc.), variation-specific
- `monthlySoldHistory[]` → [keepaTime, monthlySold, ...]
- `salesRankReference` → main BSR category (-1=unavailable, -2=launchpad)
- `salesRankReferenceHistory[]` → [keepaTime, catId, ...]
- `salesRanks` → `{ "categoryId": [keepaTime, rank, ...] }`

**Reviews:** `reviews` → { lastUpdate, reviewCount: [keepaTime, count, ...] } (requires rating param)

**Special Flags:** `batteriesRequired`, `batteriesIncluded`, `isEligibleForTradeIn`, `isAdultProduct`, `isHeatSensitive`, `isMerchOnDemand`, `isHaul`, `launchpad`, `isEligibleForSuperSaverShipping`

### CSV Array Indices (Price History)

| Index | Type | Description | Needs `offers` param? |
|-------|------|-------------|----------------------|
| 0 | AMAZON | Amazon price | No |
| 1 | NEW | Marketplace New (lowest landing price post Feb 23, 2026) | No |
| 2 | USED | Marketplace Used | No |
| 3 | SALES | Sales rank | No |
| 4 | LISTPRICE | MSRP | No |
| 5 | COLLECTIBLE | Collectible price | No |
| 6 | REFURBISHED | Refurbished price | No |
| 7 | NEW_FBM_SHIPPING | New FBM + shipping | **Yes** |
| 8 | LIGHTNING_DEAL | Lightning deal price | No |
| 9 | WAREHOUSE | Amazon Warehouse | **Yes** |
| 10 | NEW_FBA | Lowest 3P FBA price | **Yes** |
| 11 | COUNT_NEW | New offer count | **Yes** |
| 12 | COUNT_USED | Used offer count | **Yes** |
| 13 | COUNT_REFURBISHED | Refurbished offer count | **Yes** |
| 14 | COUNT_COLLECTIBLE | Collectible offer count | **Yes** |
| 15 | EXTRA_INFO_UPDATES | Update history for offers, aPlus, videos | **Yes** |
| 16 | RATING | Rating (0-50 scale) | **Yes** |
| 17 | COUNT_REVIEWS | Rating count (deprecated Apr 2025) | **Yes** |
| 18 | BUY_BOX_SHIPPING | New Buy Box + shipping | **Yes** |
| 19 | USED_NEW_SHIPPING | Used Like New + shipping | **Yes** |
| 20 | USED_VERY_GOOD_SHIPPING | Used Very Good + shipping | **Yes** |
| 21 | USED_GOOD_SHIPPING | Used Good + shipping | **Yes** |
| 22 | USED_ACCEPTABLE_SHIPPING | Used Acceptable + shipping | **Yes** |
| 23-26 | COLLECTIBLE_*_SHIPPING | Collectible conditions + shipping | **Yes** |
| 27 | REFURBISHED_SHIPPING | Refurbished + shipping | **Yes** |
| 28-29 | EBAY_*_SHIPPING | eBay prices (often inaccurate) | No |
| 30 | TRADE_IN | Trade-in price (US only) | No |
| 31 | RENTAL | Rental price (US only, requires rental + offers) | **Yes** |
| 32 | BUY_BOX_USED_SHIPPING | Used Buy Box + shipping | **Yes** |
| 33 | PRIME_EXCL | Prime Exclusive New price | **Yes** |
| **34** | **COUNT_NEW_FBA** | **New FBA offer count (incl Amazon)** | **Yes** |
| **35** | **COUNT_NEW_FBM** | **New FBM offer count** | **Yes** |

**CSV Notes:**
- Only appended when value changes (not every update)
- -1 = no offer in interval
- Shipping types: `[keepaTime, price, shipping, ...]` (triplets)
- CSV indices 34 & 35 added Feb 17, 2026

---

### Marketplace Offer Object

| Field | Type | Description |
|-------|------|-------------|
| `offerId` | String | Unique ID within product |
| `lastSeen` | Int | Last update (Keepa Time) |
| `sellerId` | String | Merchant ID |
| `isFBA` | Bool | Fulfilled by Amazon |
| `isPrime` | Bool | Prime eligible |
| `isAmazon` | Bool | Amazon.com seller |
| `isShippable` | Bool | Currently shippable |
| `isWarehouseDeal` | Bool | Warehouse deal |
| `isPreorder` | Bool | Pre-order |
| `isMAP` | Bool | Hidden price (MAP restriction) |
| `isPrimeExcl` | Bool | Prime exclusive pricing |
| `condition` | Int | 1=New, 2-5=Used variants, 6=Refurbished, 7-10=Collectible, 11=Rental |
| `conditionComment` | String | Condition description |
| `coupon` | Int | Positive=absolute $, Negative=% |
| `couponHistory` | [Int] | Historical coupon data |
| `minOrderQty` | Int | Minimum purchase quantity |
| `offerCSV` | [Int] | Price history: [time, price, shipping, ...] |
| `stockCSV` | [Int] | Stock history: [time, qty, ...] |
| `primeExclCSV` | [Int] | Prime exclusive price history |
| `offerDuplicates` | Array | Identical offers excluded (more expensive) |
| `lastStockUpdate` | Int | Last stock data update |

---

### Seller Object

| Field | Type | Description |
|-------|------|-------------|
| `sellerId` | String | Merchant ID |
| `sellerName` | String | Display name |
| `domainId` | Int | Amazon locale |
| `trackingSince` | Int | When tracking started |
| `lastUpdate` | Int | Last basic data update |
| `lastRatingUpdate` | Int | Last rating update |
| **Business Info** | | |
| `businessName` | String | Legal business name |
| `address` | [String] | Business address (last entry = country code) |
| `tradeNumber` | String | Trade register number |
| `vatID` | String | VAT number |
| `phoneNumber` | String | Phone |
| `businessType` | String | Business type |
| `shareCapital` | String | Share capital |
| `representative` | String | Business representative |
| `email` | String | Business email |
| `customerServicesAddress` | [String] | Customer service address |
| **Ratings** | | |
| `ratingCount` | [Int] | Rating counts: [30d, 90d, 365d, lifetime] |
| `positiveRating` | [Int] | Positive % across 4 periods |
| `negativeRating` | [Int] | Negative % across 4 periods |
| `neutralRating` | [Int] | Neutral % across 4 periods |
| `recentFeedback` | Array | Up to 5 recent feedbacks: date, rating, isStriked |
| `csv` | 2D [Int] | Historical rating + count data |
| **Storefront** | | |
| `hasFBA` | Bool | Has FBA listings |
| `asinList` | [String] | Up to 100,000 storefront ASINs |
| `asinListLastSeen` | [Int] | Last verification time per ASIN |
| `totalStorefrontAsins` | [Int] | [timestamp, count] history |
| **Analytics** | | |
| `sellerCategoryStatistics` | Array | Per-category: catId, productCount, avg30SalesRank, productCountWithAmazonOffer |
| `sellerBrandStatistics` | Array | Per-brand: brand, productCount, avg30SalesRank |
| `competitors` | Array | Top 5 competing sellers |
| `avgBuyBoxCompetitors` | Float | Avg sellers competing for Buy Box |
| `buyBoxNewOwnershipRate` | Int | Avg New Buy Box ownership % |
| `buyBoxUsedOwnershipRate` | Int | Avg Used Buy Box ownership % |

---

### Deal Object

| Field | Type | Description |
|-------|------|-------------|
| `asin` | String | Product ASIN |
| `parentAsin` | String | Parent ASIN if applicable |
| `title` | String | Product title |
| `rootCat` | Long | Root category ID |
| `categories` | [Long] | Category node IDs |
| `image` | [Int] | Main image (ASCII-coded) |
| `current` | [Int] | Current prices/ranks by Price Type |
| `currentSince` | [Int] | When current value took effect |
| `deltaLast` | [Int] | Previous vs current difference |
| `delta` | 2D [Int] | Average vs current by [DateRange][PriceType] |
| `deltaPercent` | 2D [Int] | Delta as percentages |
| `avg` | 2D [Int] | Weighted averages |
| `lastUpdate` | Int | Last update time |
| `creationDate` | Int | Last price change time |
| `lightningEnd` | Int | Lightning deal end (0 if N/A) |
| `warehouseCondition` | Int | Cheapest warehouse condition (0-5) |
| `warehouseConditionComment` | String | Condition comment |

---

### Best Sellers Object

```json
{
  "domainId": Integer,
  "lastUpdate": Integer,      // Keepa Time
  "categoryId": Long,
  "asinList": String[]        // Ordered best-selling first
}
```

---

### Category Object

| Field | Type | Description |
|-------|------|-------------|
| `domainId` | Int | Amazon locale |
| `catId` | Long | Category node ID |
| `name` | String | Category name |
| `children` | [Long] | Subcategory IDs |
| `parent` | Long | Parent ID (0=root) |
| `isBrowseNode` | Bool | Standard vs promotional |
| `highestRank` / `lowestRank` | Int | BSR range in category |
| `productCount` | Int | Estimated products |
| `avgBuyBox` / `avgBuyBox90` / `avgBuyBox365` | Int | Avg buy box prices |
| `avgBuyBoxDeviation` | Int | 30-day price fluctuation |
| `avgReviewCount` | Int | Avg reviews/product |
| `avgRating` | Int | Avg rating (10-50 scale) |
| `isFBAPercent` | Float | % FBA-fulfilled |
| `soldByAmazonPercent` | Float | % sold by Amazon |
| `hasCouponPercent` | Float | % with coupons |
| `avgOfferCountNew` / `avgOfferCountUsed` | Float | Avg offers/item |
| `sellerCount` | Int | Distinct sellers |
| `brandCount` | Int | Distinct brands |
| `avgDeltaPercent30/90BuyBox` | Float | Price change % |
| `relatedCategories` | [Long] | Co-listed categories by frequency |
| `topBrands` | [String] | Top 3 brands |

---

