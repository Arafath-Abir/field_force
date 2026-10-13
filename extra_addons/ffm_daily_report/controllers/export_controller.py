# -*- coding: utf-8 -*-
import io
from datetime import datetime, date
import xlsxwriter

from odoo import http, _
from odoo.http import request, Response

MAX_EXPORT_ROWS = 5000


class FFMExportController(http.Controller):

    @http.route('/ffm/export/excel', type='http', auth='user', methods=['GET'])
    def ffm_export_excel(self, **kw):
        """Export manager analytics to Excel (.xlsx) with 5,000 row safety guard."""
        report_type = kw.get('report_type') or 'daily_analysis'
        date_from_str = kw.get('date_from')
        date_to_str = kw.get('date_to')
        employee_id = kw.get('employee_id')
        asm_id = kw.get('asm_id')

        # Model mapping
        model_map = {
            'daily_analysis': 'ffm.daily.report.analysis',
            'territory_attendance': 'ffm.report.territory.attendance',
            'visits': 'ffm.report.visit.analysis',
            'journeys': 'ffm.report.journey.analysis',
            'expenses': 'ffm.report.expense.analysis',
        }
        model_name = model_map.get(report_type, 'ffm.daily.report.analysis')
        Model = request.env[model_name]

        # Build Domain (Record rules will automatically apply!)
        domain = []
        if date_from_str:
            domain.append(('date', '>=', date_from_str))
        if date_to_str:
            domain.append(('date', '<=', date_to_str))
        if employee_id:
            try:
                domain.append(('employee_id', '=', int(employee_id)))
            except (ValueError, TypeError):
                pass
        if asm_id:
            try:
                domain.append(('asm_id', '=', int(asm_id)))
            except (ValueError, TypeError):
                pass

        total_count = Model.search_count(domain)
        is_truncated = total_count > MAX_EXPORT_ROWS
        records = Model.search(domain, limit=MAX_EXPORT_ROWS)

        # Build Excel Workbook
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('FFM Report')

        # Formats
        header_fmt = workbook.add_format({
            'bold': True,
            'bg_color': '#107c41',
            'font_color': '#ffffff',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        warn_fmt = workbook.add_format({
            'bold': True,
            'font_color': '#b91c1c',
            'bg_color': '#fee2e2',
            'border': 1,
            'align': 'left',
        })
        num_fmt = workbook.add_format({'num_format': '#,##0.00'})
        int_fmt = workbook.add_format({'num_format': '#,##0'})
        date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd', 'align': 'center'})

        curr_row = 0

        # Warning banner if truncated
        if is_truncated:
            warn_msg = (
                f"Warning: To ensure server stability, export is capped at {MAX_EXPORT_ROWS:,} rows "
                f"(total records found: {total_count:,}). Please narrow down date filters for complete data."
            )
            worksheet.merge_range(curr_row, 0, curr_row, 9, warn_msg, warn_fmt)
            curr_row += 2

        # Headers and data rows based on report_type
        if report_type == 'daily_analysis':
            headers = [
                'Date', 'Employee', 'ASM (Area)', 'Territory', 'Working Place',
                'Status', 'Order (Tk)', 'Sale (Tk)', 'Collection (Tk)',
                'Chemists', 'Doctors', 'Farms', 'Distance (km)', 'TA Fare (Tk)', 'Total Expense (Tk)'
            ]
            for col_idx, h in enumerate(headers):
                worksheet.write(curr_row, col_idx, h, header_fmt)
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:C', 22)
            worksheet.set_column('D:E', 18)
            worksheet.set_column('F:F', 12)
            worksheet.set_column('G:O', 14)

            for rec in records:
                curr_row += 1
                worksheet.write(curr_row, 0, str(rec.date or ''), date_fmt)
                worksheet.write(curr_row, 1, rec.employee_id.name or '')
                worksheet.write(curr_row, 2, rec.asm_id.name or '')
                worksheet.write(curr_row, 3, rec.territory_id.name or '')
                worksheet.write(curr_row, 4, rec.working_place_id.name or '')
                worksheet.write(curr_row, 5, rec.state or '')
                worksheet.write(curr_row, 6, rec.total_order_tk, num_fmt)
                worksheet.write(curr_row, 7, rec.total_sale_tk, num_fmt)
                worksheet.write(curr_row, 8, rec.total_coll_tk, num_fmt)
                worksheet.write(curr_row, 9, rec.total_chemist_visited, int_fmt)
                worksheet.write(curr_row, 10, rec.total_prescriber_visited, int_fmt)
                worksheet.write(curr_row, 11, rec.total_farm_visited, int_fmt)
                worksheet.write(curr_row, 12, rec.total_distance_km, num_fmt)
                worksheet.write(curr_row, 13, rec.total_fare_tk, num_fmt)
                worksheet.write(curr_row, 14, rec.total_expense_tk, num_fmt)

        elif report_type == 'territory_attendance':
            headers = ['Date', 'Employee', 'ASM (Area)', 'Territory', 'Status', 'Reporting Time', 'Place', 'Accuracy (m)']
            for col_idx, h in enumerate(headers):
                worksheet.write(curr_row, col_idx, h, header_fmt)
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:C', 22)
            worksheet.set_column('D:D', 18)
            worksheet.set_column('E:E', 14)
            worksheet.set_column('F:G', 20)
            worksheet.set_column('H:H', 12)

            for rec in records:
                curr_row += 1
                worksheet.write(curr_row, 0, str(rec.date or ''), date_fmt)
                worksheet.write(curr_row, 1, rec.employee_id.name or '')
                worksheet.write(curr_row, 2, rec.asm_id.name or '')
                worksheet.write(curr_row, 3, rec.territory_id.name or '')
                worksheet.write(curr_row, 4, 'Present' if rec.status == 'present' else 'Absent', header_fmt if rec.status == 'present' else warn_fmt)
                worksheet.write(curr_row, 5, str(rec.reporting_time or ''))
                worksheet.write(curr_row, 6, rec.place_name or '')
                worksheet.write(curr_row, 7, rec.accuracy, num_fmt)

        elif report_type == 'visits':
            headers = [
                'Date', 'Employee', 'ASM (Area)', 'Type', 'Customer / Facility',
                'Doctor Grade', 'Order (Tk)', 'Sale (Tk)', 'Collection (Tk)', 'Birds Count'
            ]
            for col_idx, h in enumerate(headers):
                worksheet.write(curr_row, col_idx, h, header_fmt)
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:C', 22)
            worksheet.set_column('D:E', 25)
            worksheet.set_column('F:J', 14)

            for rec in records:
                curr_row += 1
                worksheet.write(curr_row, 0, str(rec.date or ''), date_fmt)
                worksheet.write(curr_row, 1, rec.employee_id.name or '')
                worksheet.write(curr_row, 2, rec.asm_id.name or '')
                worksheet.write(curr_row, 3, (rec.visit_type or '').title())
                worksheet.write(curr_row, 4, rec.partner_name or '')
                worksheet.write(curr_row, 5, (rec.grade or '').upper())
                worksheet.write(curr_row, 6, rec.order_tk, num_fmt)
                worksheet.write(curr_row, 7, rec.sale_tk, num_fmt)
                worksheet.write(curr_row, 8, rec.coll_tk, num_fmt)
                worksheet.write(curr_row, 9, rec.bird_count, int_fmt)

        elif report_type == 'expenses':
            headers = [
                'Date', 'Employee', 'ASM (Area)', 'Entertainment', 'Courier',
                'Photocopy', 'Hotel Rent', 'Promotion', 'Stationery', 'Carrying', 'Banking', 'Bike', 'Total (Tk)'
            ]
            for col_idx, h in enumerate(headers):
                worksheet.write(curr_row, col_idx, h, header_fmt)
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:C', 22)
            worksheet.set_column('D:M', 14)

            for rec in records:
                curr_row += 1
                worksheet.write(curr_row, 0, str(rec.date or ''), date_fmt)
                worksheet.write(curr_row, 1, rec.employee_id.name or '')
                worksheet.write(curr_row, 2, rec.asm_id.name or '')
                worksheet.write(curr_row, 3, rec.entertainment, num_fmt)
                worksheet.write(curr_row, 4, rec.courier, num_fmt)
                worksheet.write(curr_row, 5, rec.photocopy, num_fmt)
                worksheet.write(curr_row, 6, rec.hotel_rent, num_fmt)
                worksheet.write(curr_row, 7, rec.promotion, num_fmt)
                worksheet.write(curr_row, 8, rec.stationery, num_fmt)
                worksheet.write(curr_row, 9, rec.carrying, num_fmt)
                worksheet.write(curr_row, 10, rec.banking, num_fmt)
                worksheet.write(curr_row, 11, rec.bike, num_fmt)
                worksheet.write(curr_row, 12, rec.total_amount, num_fmt)

        workbook.close()
        output.seek(0)

        filename = f"FFM_{report_type.title()}_{date.today().strftime('%Y%m%d')}.xlsx"
        return Response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
            ]
        )
