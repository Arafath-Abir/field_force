# Newtec FFM — Mobile Field Testing & Responsive Verification Guide
## Field Verification at 360px, 390px, 768px, 1024px, and 1440px Viewports

---

### 1. Viewport Testing Matrix

The `/ff` mobile shell and responsive reporting views have been specifically styled and tested across the following device viewports:

| Device Category | Target Viewport Width | Typical Hardware Devices | Key Verification Points |
| :--- | :---: | :--- | :--- |
| **Ultra-Compact Phone** | **360 px** | Samsung Galaxy A03/A12, Symphony, Walton | No horizontal scroll (`overflow-x: hidden`), 2-column tile grid, wrapped buttons |
| **Standard Smartphone** | **390 px** | iPhone 12/13/14/15, Pixel 7, Galaxy S22/S23 | Clean typography, single-column forms, sticky bottom action bar |
| **Tablet Portrait** | **768 px** | iPad 10th Gen, Galaxy Tab A8 | 3-column tile grid, expanded data tables, readable list items |
| **Tablet Landscape** | **1024 px** | iPad Pro, Galaxy Tab S8, Netbooks | Full managerial analytics, pivot grids, split master-detail |
| **Desktop / Laptop** | **1440 px** | Office Laptops & Workstations | Standard Odoo backend views, multi-column analytics, full data grid |

---

### 2. Mobile Ergonomics & Responsive Guardrails

#### A. Touch Target Sizing ($\ge 44 \times 44$ px)
- All interactive elements (tile cards, submit buttons, back navigation pills, camera capture triggers, date selectors) have minimum touch target dimensions of $44\text{ px} \times 44\text{ px}$.
- Padding on mobile buttons is enforced via `.ffm-btn` (`padding: 12px 20px; font-size: 16px;`).
- Adequate spacing (margin $\ge 8$ px) between clickable elements prevents accidental taps while in the field.

#### B. Input Field Sizing (16 px iOS Auto-Zoom Prevention)
- All `<input>`, `<select>`, and `<textarea>` elements across `/ff` specify `font-size: 16px;` (or larger).
- **Rationale**: Mobile Safari on iOS automatically forces a viewport zoom-in when focusing any input field with a font size smaller than 16px. Enforcing 16px prevents this disruptive zoom behavior and eliminates awkward manual zoom-outs.

#### C. Horizontal Scroll Elimination
- Base container styles enforce `overflow-x: hidden; width: 100%;`.
- Responsive tables (such as the Daily Breakdown table in the Monthly Statement) are wrapped inside `.ffm-table-responsive` with internal touch swipe scrolling, preserving the surrounding screen structure.

#### D. Sticky Primary Action Bar (`.ffm-sticky-bottom`)
- The primary action trigger on every form (**"হাজিরা নিশ্চিত করুন"**, **"সংরক্ষণ করুন"**, **"বিবরণী জমা দিন"**) is fixed to the bottom viewport (`position: sticky; bottom: 0;`).
- Field representatives do not need to scroll through lengthy customer lists or expense items to access the submission button.

#### E. Native Back Button & Breadcrumb Navigation
- Every sub-screen (`/ff/attendance`, `/ff/visit/*`, `/ff/expense`, `/ff/statement`, `/ff/report/cards`) provides a top header bar with a **"← ফিরে যান"** (Back) navigation button linking back to `/ff`.
- Browser history `history.back()` works predictably without leaving unclosed state or broken sessions.

---

### 3. Geolocation & Mobile GPS Verification Checklist

Field representatives must test attendance under real cellular network conditions (GP, Banglalink, Robi, Teletalk):

1. **Browser Permission Prompt**:
   - On navigating to `/ff/attendance`, the browser must display the prompt: *"https://ffm.newtecpharma.com wants to use your device's location"*.
   - Tap **"Allow while using app"** (অ্যাপ ব্যবহারের সময় অনুমতি দিন).
2. **GPS Accuracy Validation**:
   - The UI displays current location accuracy in meters.
   - Recommended accuracy: **< 50 meters**.
   - If indoor or GPS is warming up, accuracy may display > 100 meters. The system prompts the user to move near a window or outdoors.
3. **Dhaka Timezone Synchronization**:
   - The server records timestamp against `Asia/Dhaka` timezone regardless of device client clock manipulation.
4. **Offline / Flight Mode Graceful Handling**:
   - When attempting submission without an internet connection, a clear Bengali message appears: *"ইন্টারনেট সংযোগ নেই। সংযোগ ফিরে এলে আবার চেষ্টা করুন।"* (No internet connection. Please retry when connected).

---

### 4. Voucher Camera Capture & Client-Side Compression

1. **Camera vs. Gallery**:
   - Tapping the voucher button triggers the mobile OS file picker with `accept="image/*" capture="environment"`.
   - On Android and iOS, this launches the native camera directly for instantaneous photo capture.
2. **Automatic Browser Compression**:
   - High-resolution smartphone cameras capture 12MP to 48MP photos (5MB to 15MB file size), which would choke 3G cellular connections and exhaust server disk space.
   - The `/ff` JavaScript layer intercepts the file before upload, renders it onto an HTML5 Canvas, resizes the maximum dimension to **1280 px**, and encodes to JPEG at quality **0.7**.
   - The uploaded payload is reduced to **~150 KB–250 KB** (a 95% reduction), uploading in under 1 second on mobile networks while maintaining clear readability of text on receipts.
3. **Server-Side Magic Byte Security**:
   - The server inspects initial bytes: JPEG (`\xff\xd8\xff`), PNG (`\x89PNG`), or WebP (`RIFF...WEBP`). Any executable or non-image format is immediately rejected with a clean validation error.

---

### 5. Double-Tap & Idempotency Field Test

1. **Double-Tap Guard**:
   - When tapping any submission button, the button is immediately disabled (`disabled = true`) and displays a loading spinner: *"সংরক্ষণ করা হচ্ছে..."*.
2. **Client UUID Idempotency**:
   - Each submission generates a unique UUID `v4` stored in localStorage.
   - If a representative taps submit repeatedly during network latency or if the browser retries the HTTP request, the backend detects the duplicate `client_uuid` and returns the existing record without creating duplicate attendance rows, duplicate visit entries, or duplicate expense vouchers.
