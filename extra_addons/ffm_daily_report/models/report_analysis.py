# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class FFMDailyReportAnalysis(models.Model):
    _name = 'ffm.daily.report.analysis'
    _description = 'Daily Report & Performance Analysis'
    _auto = False
    _order = 'date desc, id desc'

    id = fields.Integer(string='ID', readonly=True)
    report_id = fields.Many2one('ffm.daily.report', string='Daily Report', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    asm_id = fields.Many2one('hr.employee', string='ASM / Area Manager', readonly=True)
    rsm_id = fields.Many2one('hr.employee', string='RSM / Regional Manager', readonly=True)
    territory_id = fields.Many2one('territory.territory', string='Territory', readonly=True)
    working_place_id = fields.Many2one('ffm.place', string='Working Place', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', readonly=True)

    total_order_tk = fields.Float(string='Order (Tk)', readonly=True)
    total_sale_tk = fields.Float(string='Sale (Tk)', readonly=True)
    total_coll_tk = fields.Float(string='Collection (Tk)', readonly=True)
    total_chemist_visited = fields.Integer(string='Chemists Visited', readonly=True)
    total_prescriber_visited = fields.Integer(string='Doctors Visited', readonly=True)
    total_farm_visited = fields.Integer(string='Farms Visited', readonly=True)
    total_distance_km = fields.Float(string='Distance (km)', readonly=True)
    total_fare_tk = fields.Float(string='TA / Fare (Tk)', readonly=True)
    total_expense_tk = fields.Float(string='Expense (Tk)', readonly=True)

    entertainment_tk = fields.Float(string='Entertainment (Tk)', readonly=True)
    courier_tk = fields.Float(string='Courier (Tk)', readonly=True)
    photocopy_tk = fields.Float(string='Photocopy (Tk)', readonly=True)
    hotel_rent_tk = fields.Float(string='Hotel Rent (Tk)', readonly=True)
    promotion_tk = fields.Float(string='Promotion (Tk)', readonly=True)
    stationery_tk = fields.Float(string='Stationery (Tk)', readonly=True)
    carrying_tk = fields.Float(string='Carrying (Tk)', readonly=True)
    banking_tk = fields.Float(string='Banking (Tk)', readonly=True)
    bike_tk = fields.Float(string='Bike (Tk)', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    dr.id AS id,
                    dr.id AS report_id,
                    dr.date AS date,
                    dr.employee_id AS employee_id,
                    emp.user_id AS user_id,
                    emp.parent_id AS asm_id,
                    asm.parent_id AS rsm_id,
                    dr.territory_id AS territory_id,
                    dr.working_place_id AS working_place_id,
                    dr.state AS state,
                    COALESCE(chem_agg.total_order_tk, dr.total_order_tk, 0.0) AS total_order_tk,
                    COALESCE(chem_agg.total_sale_tk, dr.total_sale_tk, 0.0) AS total_sale_tk,
                    COALESCE(chem_agg.total_coll_tk, dr.total_coll_tk, 0.0) AS total_coll_tk,
                    COALESCE(chem_agg.total_chemist_visited, dr.total_chemist_visited, 0) AS total_chemist_visited,
                    COALESCE(doc_agg.total_prescriber_visited, dr.total_prescriber_visited, 0) AS total_prescriber_visited,
                    COALESCE(farm_agg.total_farm_visited, dr.total_farm_visited, 0) AS total_farm_visited,
                    COALESCE(travel_agg.total_distance_km, tl.total_distance_km, 0.0) AS total_distance_km,
                    COALESCE(travel_agg.total_fare_tk, tl.total_fare_tk, 0.0) AS total_fare_tk,
                    COALESCE(exp_agg.total_expense, dr.total_expense_tk, 0.0) AS total_expense_tk,
                    COALESCE(exp_agg.entertainment, 0.0) AS entertainment_tk,
                    COALESCE(exp_agg.courier, 0.0) AS courier_tk,
                    COALESCE(exp_agg.photocopy, 0.0) AS photocopy_tk,
                    COALESCE(exp_agg.hotel_rent, 0.0) AS hotel_rent_tk,
                    COALESCE(exp_agg.promotion, 0.0) AS promotion_tk,
                    COALESCE(exp_agg.stationery, 0.0) AS stationery_tk,
                    COALESCE(exp_agg.carrying, 0.0) AS carrying_tk,
                    COALESCE(exp_agg.banking, 0.0) AS banking_tk,
                    COALESCE(exp_agg.bike, 0.0) AS bike_tk
                FROM ffm_daily_report dr
                JOIN hr_employee emp ON emp.id = dr.employee_id
                LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
                LEFT JOIN hr_employee rsm ON rsm.id = asm.parent_id
                LEFT JOIN ffm_travel_log tl ON tl.daily_report_id = dr.id
                LEFT JOIN (
                    SELECT
                        tl_inner.daily_report_id,
                        SUM(tj.distance_km) AS total_distance_km,
                        SUM(tj.fare_tk) AS total_fare_tk
                    FROM ffm_travel_journey tj
                    JOIN ffm_travel_log tl_inner ON tl_inner.id = tj.travel_log_id
                    WHERE tl_inner.daily_report_id IS NOT NULL
                    GROUP BY tl_inner.daily_report_id
                ) travel_agg ON travel_agg.daily_report_id = dr.id
                LEFT JOIN (
                    SELECT
                        report_id,
                        SUM(order_tk) AS total_order_tk,
                        SUM(sale_tk) AS total_sale_tk,
                        SUM(coll_tk) AS total_coll_tk,
                        COUNT(id) AS total_chemist_visited
                    FROM ffm_chemist_visit
                    GROUP BY report_id
                ) chem_agg ON chem_agg.report_id = dr.id
                LEFT JOIN (
                    SELECT
                        report_id,
                        COUNT(id) AS total_prescriber_visited
                    FROM ffm_prescriber_visit
                    GROUP BY report_id
                ) doc_agg ON doc_agg.report_id = dr.id
                LEFT JOIN (
                    SELECT
                        report_id,
                        COUNT(id) AS total_farm_visited
                    FROM ffm_farm_visit
                    GROUP BY report_id
                ) farm_agg ON farm_agg.report_id = dr.id
                LEFT JOIN (
                    SELECT
                        daily_report_id,
                        SUM(COALESCE(entertainment, 0) + COALESCE(courier, 0) + COALESCE(photocopy, 0) +
                            COALESCE(hotel_rent, 0) + COALESCE(promotion, 0) + COALESCE(stationery, 0) +
                            COALESCE(carrying, 0) + COALESCE(banking, 0) + COALESCE(bike, 0)) AS total_expense,
                        SUM(entertainment) AS entertainment,
                        SUM(courier) AS courier,
                        SUM(photocopy) AS photocopy,
                        SUM(hotel_rent) AS hotel_rent,
                        SUM(promotion) AS promotion,
                        SUM(stationery) AS stationery,
                        SUM(carrying) AS carrying,
                        SUM(banking) AS banking,
                        SUM(bike) AS bike
                    FROM ffm_daily_expense
                    WHERE daily_report_id IS NOT NULL
                    GROUP BY daily_report_id
                ) exp_agg ON exp_agg.daily_report_id = dr.id
            )
        """ % self._table)


class FFMReportTerritoryAttendance(models.Model):
    _name = 'ffm.report.territory.attendance'
    _description = 'Daily Territory Attendance Analysis'
    _auto = False
    _order = 'date desc, employee_id asc'

    id = fields.Integer(string='ID', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    asm_id = fields.Many2one('hr.employee', string='ASM / Area Manager', readonly=True)
    rsm_id = fields.Many2one('hr.employee', string='RSM / Regional Manager', readonly=True)
    territory_id = fields.Many2one('territory.territory', string='Territory', readonly=True)
    attendance_id = fields.Many2one('ffm.attendance', string='Attendance Record', readonly=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent / Pending'),
    ], string='Status', readonly=True)
    is_present = fields.Integer(string='Present Count', readonly=True)
    is_absent = fields.Integer(string='Absent Count', readonly=True)
    reporting_time = fields.Datetime(string='Reporting Time', readonly=True)
    working_place_id = fields.Many2one('ffm.place', string='Working Place', readonly=True)
    mode_of_journey = fields.Char(string='Mode of Journey', readonly=True)
    latitude = fields.Float(string='Latitude', readonly=True)
    longitude = fields.Float(string='Longitude', readonly=True)
    accuracy = fields.Float(string='Accuracy (m)', readonly=True)
    place_name = fields.Char(string='Place / Location', readonly=True)

    def get_reporting_time_bd(self, fmt='%I:%M %p'):
        self.ensure_one()
        if not self.reporting_time:
            return ''
        dhaka_tz = pytz.timezone('Asia/Dhaka')
        utc_dt = pytz.utc.localize(self.reporting_time)
        return utc_dt.astimezone(dhaka_tz).strftime(fmt)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH distinct_dates AS (
                    SELECT DISTINCT date FROM ffm_attendance
                    UNION
                    SELECT CURRENT_DATE
                ),
                emp_dates AS (
                    SELECT
                        emp.id AS employee_id,
                        emp.user_id AS user_id,
                        emp.parent_id AS asm_id,
                        asm.parent_id AS rsm_id,
                        emp.hq AS hq,
                        d.date AS date
                    FROM hr_employee emp
                    CROSS JOIN distinct_dates d
                    LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
                    WHERE emp.active = true
                )
                SELECT
                    (ed.employee_id * 10000 + (ed.date - '2020-01-01'::date))::bigint AS id,
                    ed.date AS date,
                    ed.employee_id AS employee_id,
                    ed.user_id AS user_id,
                    ed.asm_id AS asm_id,
                    ed.rsm_id AS rsm_id,
                    att.id AS attendance_id,
                    COALESCE(att.territory_id, dr.territory_id) AS territory_id,
                    dr.working_place_id AS working_place_id,
                    COALESCE(wp.name, ed.hq, 'Bangladesh') AS place_name,
                    att.reporting_time AS reporting_time,
                    att.mode_of_journey AS mode_of_journey,
                    att.latitude AS latitude,
                    att.longitude AS longitude,
                    att.accuracy AS accuracy,
                    CASE WHEN att.id IS NOT NULL THEN 'present' ELSE 'absent' END AS status,
                    CASE WHEN att.id IS NOT NULL THEN 1 ELSE 0 END AS is_present,
                    CASE WHEN att.id IS NULL THEN 1 ELSE 0 END AS is_absent
                FROM emp_dates ed
                LEFT JOIN ffm_attendance att ON att.employee_id = ed.employee_id AND att.date = ed.date
                LEFT JOIN ffm_daily_report dr ON dr.employee_id = ed.employee_id AND dr.date = ed.date
                LEFT JOIN ffm_place wp ON wp.id = dr.working_place_id
            )
        """ % self._table)


class FFMReportVisitAnalysis(models.Model):
    _name = 'ffm.report.visit.analysis'
    _description = 'Field Visits Analysis'
    _auto = False
    _order = 'date desc, id desc'

    id = fields.Integer(string='ID', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    asm_id = fields.Many2one('hr.employee', string='ASM / Area Manager', readonly=True)
    rsm_id = fields.Many2one('hr.employee', string='RSM / Regional Manager', readonly=True)
    territory_id = fields.Many2one('territory.territory', string='Territory', readonly=True)
    working_place_id = fields.Many2one('ffm.place', string='Working Place', readonly=True)
    visit_type = fields.Selection([
        ('chemist', 'Chemist'),
        ('doctor', 'Doctor'),
        ('farm', 'Farm & Others'),
    ], string='Visit Type', readonly=True)
    partner_name = fields.Char(string='Customer / Facility Name', readonly=True)
    grade = fields.Char(string='Grade', readonly=True)
    order_tk = fields.Float(string='Order (Tk)', readonly=True)
    sale_tk = fields.Float(string='Sale (Tk)', readonly=True)
    coll_tk = fields.Float(string='Collection (Tk)', readonly=True)
    bird_count = fields.Integer(string='Bird / Animal Count', readonly=True)
    visit_count = fields.Integer(string='Visits Count', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH combined_visits AS (
                    -- Chemist Visits
                    SELECT
                        dr.date AS date,
                        dr.employee_id AS employee_id,
                        emp.user_id AS user_id,
                        emp.parent_id AS asm_id,
                        asm.parent_id AS rsm_id,
                        dr.territory_id AS territory_id,
                        dr.working_place_id AS working_place_id,
                        'chemist'::varchar AS visit_type,
                        COALESCE(ci.name, cv.chemist_name_manual, 'Unknown Chemist')::varchar AS partner_name,
                        NULL::varchar AS grade,
                        COALESCE(cv.order_tk, 0.0) AS order_tk,
                        COALESCE(cv.sale_tk, 0.0) AS sale_tk,
                        COALESCE(cv.coll_tk, 0.0) AS coll_tk,
                        0 AS bird_count,
                        1 AS visit_count
                    FROM ffm_chemist_visit cv
                    JOIN ffm_daily_report dr ON dr.id = cv.report_id
                    JOIN hr_employee emp ON emp.id = dr.employee_id
                    LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
                    LEFT JOIN customer_information ci ON ci.id = cv.chemist_id

                    UNION ALL

                    -- Doctor Visits
                    SELECT
                        dr.date AS date,
                        dr.employee_id AS employee_id,
                        emp.user_id AS user_id,
                        emp.parent_id AS asm_id,
                        asm.parent_id AS rsm_id,
                        dr.territory_id AS territory_id,
                        dr.working_place_id AS working_place_id,
                        'doctor'::varchar AS visit_type,
                        COALESCE(ci.name, pv.prescriber_name_manual, 'Unknown Doctor')::varchar AS partner_name,
                        pv.grade::varchar AS grade,
                        0.0 AS order_tk,
                        0.0 AS sale_tk,
                        0.0 AS coll_tk,
                        0 AS bird_count,
                        1 AS visit_count
                    FROM ffm_prescriber_visit pv
                    JOIN ffm_daily_report dr ON dr.id = pv.report_id
                    JOIN hr_employee emp ON emp.id = dr.employee_id
                    LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
                    LEFT JOIN customer_information ci ON ci.id = pv.prescriber_id

                    UNION ALL

                    -- Farm Visits
                    SELECT
                        dr.date AS date,
                        dr.employee_id AS employee_id,
                        emp.user_id AS user_id,
                        emp.parent_id AS asm_id,
                        asm.parent_id AS rsm_id,
                        dr.territory_id AS territory_id,
                        dr.working_place_id AS working_place_id,
                        'farm'::varchar AS visit_type,
                        fv.farm_name::varchar AS partner_name,
                        NULL::varchar AS grade,
                        0.0 AS order_tk,
                        0.0 AS sale_tk,
                        0.0 AS coll_tk,
                        COALESCE(fv.bird_count, 0) AS bird_count,
                        1 AS visit_count
                    FROM ffm_farm_visit fv
                    JOIN ffm_daily_report dr ON dr.id = fv.report_id
                    JOIN hr_employee emp ON emp.id = dr.employee_id
                    LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
                )
                SELECT
                    row_number() OVER () AS id,
                    *
                FROM combined_visits
            )
        """ % self._table)


class FFMReportJourneyAnalysis(models.Model):
    _name = 'ffm.report.journey.analysis'
    _description = 'Field Journey & Travel Analysis'
    _auto = False
    _order = 'date desc, id desc'

    id = fields.Integer(string='ID', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    asm_id = fields.Many2one('hr.employee', string='ASM / Area Manager', readonly=True)
    rsm_id = fields.Many2one('hr.employee', string='RSM / Regional Manager', readonly=True)
    territory_id = fields.Many2one('territory.territory', string='Territory', readonly=True)
    place_from_id = fields.Many2one('ffm.place', string='From Place', readonly=True)
    place_to_id = fields.Many2one('ffm.place', string='To Place', readonly=True)
    mode = fields.Selection([
        ('bus', 'Bus'),
        ('rickshaw', 'Rickshaw'),
        ('auto_cng', 'Auto / CNG'),
        ('motorcycle', 'Motorcycle'),
        ('uber_pathao', 'Uber / Pathao'),
        ('on_foot', 'On Foot'),
        ('train', 'Train'),
        ('launch', 'Launch / Ferry'),
        ('others', 'Others'),
    ], string='Mode of Journey', readonly=True)
    distance_km = fields.Float(string='Distance (km)', readonly=True)
    fare_tk = fields.Float(string='Fare (Tk)', readonly=True)
    journey_count = fields.Integer(string='Journey Legs Count', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    tj.id AS id,
                    tl.date AS date,
                    tl.employee_id AS employee_id,
                    emp.user_id AS user_id,
                    emp.parent_id AS asm_id,
                    asm.parent_id AS rsm_id,
                    tl.territory_id AS territory_id,
                    tj.place_from_id AS place_from_id,
                    tj.place_to_id AS place_to_id,
                    tj.mode AS mode,
                    COALESCE(tj.distance_km, 0.0) AS distance_km,
                    COALESCE(tj.fare_tk, 0.0) AS fare_tk,
                    1 AS journey_count
                FROM ffm_travel_journey tj
                JOIN ffm_travel_log tl ON tl.id = tj.travel_log_id
                JOIN hr_employee emp ON emp.id = tl.employee_id
                LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
            )
        """ % self._table)


class FFMReportExpenseAnalysis(models.Model):
    _name = 'ffm.report.expense.analysis'
    _description = 'Field Expense Analysis'
    _auto = False
    _order = 'date desc, id desc'

    id = fields.Integer(string='ID', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    asm_id = fields.Many2one('hr.employee', string='ASM / Area Manager', readonly=True)
    rsm_id = fields.Many2one('hr.employee', string='RSM / Regional Manager', readonly=True)
    daily_report_id = fields.Many2one('ffm.daily.report', string='Daily Report', readonly=True)
    entertainment = fields.Float(string='Entertainment (Tk)', readonly=True)
    courier = fields.Float(string='Courier (Tk)', readonly=True)
    photocopy = fields.Float(string='Photocopy (Tk)', readonly=True)
    hotel_rent = fields.Float(string='Hotel Rent (Tk)', readonly=True)
    promotion = fields.Float(string='Promotion (Tk)', readonly=True)
    stationery = fields.Float(string='Stationery (Tk)', readonly=True)
    carrying = fields.Float(string='Carrying (Tk)', readonly=True)
    banking = fields.Float(string='Banking (Tk)', readonly=True)
    bike = fields.Float(string='Bike (Tk)', readonly=True)
    total_amount = fields.Float(string='Total Expense (Tk)', readonly=True)
    expense_count = fields.Integer(string='Expense Records Count', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    exp.id AS id,
                    exp.date AS date,
                    exp.employee_id AS employee_id,
                    emp.user_id AS user_id,
                    emp.parent_id AS asm_id,
                    asm.parent_id AS rsm_id,
                    exp.daily_report_id AS daily_report_id,
                    COALESCE(exp.entertainment, 0.0) AS entertainment,
                    COALESCE(exp.courier, 0.0) AS courier,
                    COALESCE(exp.photocopy, 0.0) AS photocopy,
                    COALESCE(exp.hotel_rent, 0.0) AS hotel_rent,
                    COALESCE(exp.promotion, 0.0) AS promotion,
                    COALESCE(exp.stationery, 0.0) AS stationery,
                    COALESCE(exp.carrying, 0.0) AS carrying,
                    COALESCE(exp.banking, 0.0) AS banking,
                    COALESCE(exp.bike, 0.0) AS bike,
                    (COALESCE(exp.entertainment, 0.0) + COALESCE(exp.courier, 0.0) + COALESCE(exp.photocopy, 0.0) +
                     COALESCE(exp.hotel_rent, 0.0) + COALESCE(exp.promotion, 0.0) + COALESCE(exp.stationery, 0.0) +
                     COALESCE(exp.carrying, 0.0) + COALESCE(exp.banking, 0.0) + COALESCE(exp.bike, 0.0)) AS total_amount,
                    1 AS expense_count
                FROM ffm_daily_expense exp
                JOIN hr_employee emp ON emp.id = exp.employee_id
                LEFT JOIN hr_employee asm ON asm.id = emp.parent_id
            )
        """ % self._table)
