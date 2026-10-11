# Newtec FFM — Role-Based User Manual
## Operational Guide for Field Personnel, Management, and Accounts

---

### 1. Field Person (Medical Information Officer / Marketer)

#### A. Login and Mobile PWA Setup
1. Open mobile browser (Chrome on Android or Safari on iOS) and navigate to: `http://<SERVER_IP>:8069/ff`.
2. Tap the browser menu and select **"Add to Home screen"** (হோம் স্ক্রিনে যোগ করুন) for full-screen PWA experience.
3. Marketers logging into `/web` are automatically redirected to the fast `/ff` portal.

#### B. Daily Morning Attendance (হাজিরা)
1. Tap the **"হাজিরা (Attendance)"** tile.
2. Grant browser GPS location permissions. Ensure location accuracy is good (< 100 meters).
3. The server validates time in the **Asia/Dhaka** timezone.
4. Tap **"হাজিরা নিশ্চিত করুন"**. Once submitted, attendance is locked for the day. Marking attendance again is safely prevented.

#### C. Working Place & Daily Field Visits
1. **Working Place (কর্মস্থল)**: On the first visit of the day, choose your designated working place (`ffm.place`).
2. **Chemist Shop Visit (কেমিস্ট ভিজিট)**:
   - Select an existing chemist from the live search list, or enter a manual name.
   - Enter **Order (Tk)**, **Sale (Tk)**, and **Collection (Tk)** (positive whole numbers).
   - If travel occurred, fill the **Journey Block**: From Place, To Place, Transport Mode (Motorcycle, Bus, CNG, etc.), Distance, and Fare.
   - Tap **"সংরক্ষণ করুন"**.
3. **Doctor Visit (ডাক্তার ভিজিট)**:
   - Search doctor or input manual name, contact, address, product discussion, sample distributed, and doctor grade (A+, A, B, C).
   - Complete the Journey Block if traveled.
4. **Farm & Others Visit (ফার্ম ও অন্যান্য ভিজিট)**:
   - Enter farm name, address, and bird/livestock details (Broiler, Layer, Sonali, Cattle, Aqua, bird count).
   - Complete the Journey Block if traveled.

#### D. Daily Operational Expenses (দৈনিক খরচ ও ভাউচার)
1. Tap the **"দৈনিক খরচ (Expense)"** tile.
2. Enter expense amounts across the 9 approved heads:
   - Entertainment (আপ্যায়ন) *
   - Postage / Courier (ডাক ও কুরিয়ার) *
   - Photocopy (ফটোকপি) *
   - Promotion (প্রমোশন)
   - Stationery (স্টেশনারি)
   - Carrying Charge (বহন খরচ)
   - Banking Charge (ব্যাংক চার্জ)
   - Hotel Rent (হোটেল ভাড়া) *
   - Motorcycle Fuel / Other Bike (মোটরসাইকেল জ্বালানি)
3. **Mandatory Vouchers (*)**: When an amount is entered for Entertainment, Courier, Photocopy, or Hotel Rent, a voucher image is strictly required. Take a photo or upload from the gallery. Images are automatically compressed in your mobile browser before upload.
4. Tap **"খরচ সংরক্ষণ করুন"**.

#### E. Monthly Expense Statement (মাসিক খরচের বিবরণী)
1. At month-end, tap **"মাসিক বিবরণী (Statement)"**.
2. Select the month and year, then tap **"বিবরণী তৈরি / রিফ্রেশ"**.
3. Review your Daily Table (auto-calculated T.A. travel fares + D.A. daily allowances) and Other Expenses.
4. Add any remarks in the comments box and tap **"বিবরণী জমা দিন (Submit)"**.
5. You can download your official PDF statement at any time by clicking **"PDF ডাউনলোড"**.

---

### 2. Area Sales Manager (ASM)

1. **Territory Attendance Monitoring**:
   - In `/ff`, tap **"রিপোর্ট কার্ড"** and select **"Daily Territory Attendance"**.
   - Instantly see which Field Persons under your area have submitted attendance and who are absent.
2. **Daily Report Review**:
   - Access the backend or mobile summary to verify visit counts, chemist collections, and travel routes.
3. **Statement Checking**:
   - In the backend under **Expense Statements**, open submitted statements for your area.
   - Review visits and attached vouchers.
   - Click **"Check Statement"** to forward to the Regional Sales Manager / NSM.
   - If vouchers are invalid or unclear, click **"Reject"**, enter the mandatory rejection reason, and return it to the Field Person for correction.

---

### 3. Regional Sales Manager (RSM) & Divisional Sales Manager (DSM)

1. **Regional Oversight**:
   - Review aggregate performance across territories and ASMs.
   - Access **Field Force Management > Reports > Daily Report Analysis** for pivot views of visits, collections, and expenses.
2. **Drill-down Analytics**:
   - Filter by Region -> Area -> Individual Field Person to spot low-performing territories or unusual expense spikes.

---

### 4. National Sales Manager (NSM) / Marketing Manager (MM) & Director

1. **Statement Approval**:
   - Filter **Expense Statements** in state `Checked`.
   - Perform executive verification.
   - Click **"Approve Statement"**. This locks the statement and forwards it to Accounts for payment disbursement.
2. **Strategic BI Reports**:
   - Use pivot and graph views in **Reports** to analyze doctor coverage grades (A+ coverage percentage) and chemist collection ratios vs travel allowances.
   - Export reports directly to Excel or PDF.

---

### 5. Accounts Department

1. **Payment Processing**:
   - Navigate to **Field Force Management > Expense Statements**.
   - Filter by status **"Approved"** (অনুমোদিত).
   - Review the financial totals (T.A. + D.A. + Voucher Sum + Motorcycle Maintenance).
   - Verify voucher attachments directly in the form view.
   - Upon disbursing payment to the employee's bank or mobile wallet, click **"Mark as Paid"** (পরিশোধিত).
2. **Audit Compliance**:
   - All state transitions, check timestamps, and approver user IDs are permanently archived in the immutable **Audit Log**.

---

### 6. System Administrator

1. **Designation Allowance Maintenance**:
   - Navigate to **Configuration > Allowance Rates**. Maintain daily D.A. and monthly motorcycle maintenance per job title.
2. **Fare Configuration**:
   - Maintain slab rates per kilometer under **Configuration > Fare Slabs**.
3. **Audit Trails**:
   - View the read-only audit log at **Field Force Management > Audit Logs** to track all system actions, IP addresses, and timestamps.
