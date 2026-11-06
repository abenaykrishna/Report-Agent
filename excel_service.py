import math
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows


class ExcelService:
    @staticmethod
    def generate_workbook(
        raw_data: pd.DataFrame,
        report_data: pd.DataFrame,
        kpis: dict,
        lineage_data: pd.DataFrame,
        metadata: pd.DataFrame,
        pas_mapping: pd.DataFrame = None,
        crm_mapping: pd.DataFrame = None,
        transformation_mapping: pd.DataFrame = None,
        output_filename: str = "Insurance_Report.xlsx",
    ):
        wb = Workbook()

        # ── Shared styles ──────────────────────────────────────────────────── #
        title_font      = Font(name="Segoe UI", size=16, bold=True, color="1B365D")
        section_font    = Font(name="Segoe UI", size=12, bold=True, color="1B365D")
        header_font     = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        label_font      = Font(name="Segoe UI", size=10, bold=True, color="1B365D")
        body_font       = Font(name="Segoe UI", size=10)
        header_fill     = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
        section_fill    = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        zebra_fill      = PatternFill(start_color="F7F9FB", end_color="F7F9FB", fill_type="solid")
        accent_fill     = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
        thin_border     = Border(
            left=Side(border_style="thin", color="D3D3D3"),
            right=Side(border_style="thin", color="D3D3D3"),
            top=Side(border_style="thin", color="D3D3D3"),
            bottom=Side(border_style="thin", color="D3D3D3"),
        )
        medium_border   = Border(
            left=Side(border_style="medium", color="1B365D"),
            right=Side(border_style="medium", color="1B365D"),
            top=Side(border_style="medium", color="1B365D"),
            bottom=Side(border_style="medium", color="1B365D"),
        )

        # ── Helpers ────────────────────────────────────────────────────────── #
        def sanitise(value):
            """Convert pandas NA / NaT / NaN / inf / tz-aware datetimes to
            types that openpyxl can write safely."""
            import math
            import datetime as dt

            if value is None or value is pd.NA:
                return None
            # Convert iterable types (except string/bytes) to a string representation
            if (hasattr(value, "__iter__") and not isinstance(value, (str, bytes))) or type(value).__name__ == "ndarray":
                if isinstance(value, dict):
                    return str(value)
                try:
                    return ", ".join(map(str, value))
                except Exception:
                    return str(value)
            # pandas NaT and other NA-like types
            try:
                result = pd.isna(value)
                if bool(result):
                    return None
            except (TypeError, ValueError):
                pass
            # float NaN / inf
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            # Timezone-aware datetime → strip tzinfo so openpyxl accepts it
            if isinstance(value, dt.datetime) and value.tzinfo is not None:
                return value.replace(tzinfo=None)
            if isinstance(value, dt.time) and value.tzinfo is not None:
                return value.replace(tzinfo=None)
            return value

        def fmt_number(value):
            """Format a numeric value for display (int if whole, else 2dp)."""
            val_san = sanitise(value)
            if val_san is None:
                return None
            try:
                f = float(val_san)
                if math.isnan(f) or math.isinf(f):
                    return None
                return int(f) if f == int(f) else round(f, 2)
            except (TypeError, ValueError):
                return val_san

        def write_section_header(ws, row, col, text, width=2):
            cell = ws.cell(row=row, column=col, value=text)
            cell.font = section_font
            cell.fill = section_fill
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center")
            # Merge across width columns
            if width > 1:
                ws.merge_cells(
                    start_row=row, start_column=col,
                    end_row=row, end_column=col + width - 1,
                )

        def write_kv(ws, row, key, value, even=False):
            c1 = ws.cell(row=row, column=1, value=key)
            c2 = ws.cell(row=row, column=2, value=sanitise(value))
            c1.font = label_font
            c2.font = body_font
            c1.border = thin_border
            c2.border = thin_border
            c1.alignment = Alignment(wrap_text=True)
            if even:
                c1.fill = zebra_fill
                c2.fill = zebra_fill

        def write_df_to_sheet(ws, title, df):
            ws["A1"] = title
            ws["A1"].font = title_font
            if df.empty:
                ws["A3"] = "No data available."
                ws["A3"].font = body_font
                return
            for r_idx, row in enumerate(
                dataframe_to_rows(df, index=False, header=True), start=3
            ):
                for c_idx, value in enumerate(row, start=1):
                    cell = ws.cell(row=r_idx, column=c_idx, value=sanitise(value))
                    cell.border = thin_border
                    cell.font = body_font
                    if r_idx == 3:
                        cell.font = header_font
                        cell.fill = header_fill
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    elif r_idx % 2 == 0:
                        cell.fill = zebra_fill

            # Freeze panes below the header row (row 3)
            ws.freeze_panes = "A4"

            # Enable auto filters for the table columns
            from openpyxl.utils import get_column_letter
            max_col = get_column_letter(df.shape[1])
            max_row = 3 + df.shape[0]
            ws.auto_filter.ref = f"A3:{max_col}{max_row}"

        # ── Sheet 1: Main Report (actual raw table records) ────────────────── #
        ws_main = wb.active
        ws_main.title = "Main_Report"
        write_df_to_sheet(ws_main, "Actual Data", raw_data)


        # ── Sheet 2: Dashboard (computed metrics) ──────────────────────────── #
        ws_dash = wb.create_sheet(title="Dashboard")
        ws_dash.column_dimensions["A"].width = 38
        ws_dash.column_dimensions["B"].width = 22

        row = 1
        ws_dash.cell(row=row, column=1, value="Executive KPI Performance Dashboard").font = title_font
        row += 2

        # Section A — Report Overview (from kpis dict)
        write_section_header(ws_dash, row, 1, "📋  Report Overview")
        row += 1
        for i, (k, v) in enumerate(kpis.items()):
            write_kv(ws_dash, row, k.replace("_", " ").title(), v, even=(i % 2 == 0))
            row += 1
        row += 1

        # Section B — Numeric Column Summary (computed from report_data)
        numeric_cols = report_data.select_dtypes(include="number").columns.tolist()
        if numeric_cols and not report_data.empty:
            write_section_header(ws_dash, row, 1, "📊  Numeric Column Summary")
            row += 1
            # sub-header
            for col_idx, label in enumerate(["Metric", "Total", "Average", "Min", "Max"], start=1):
                cell = ws_dash.cell(row=row, column=col_idx, value=label)
                cell.font = header_font
                cell.fill = header_fill
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")
            ws_dash.column_dimensions["C"].width = 18
            ws_dash.column_dimensions["D"].width = 18
            ws_dash.column_dimensions["E"].width = 18
            row += 1
            for i, col_name in enumerate(numeric_cols):
                series = report_data[col_name].dropna()
                ws_dash.cell(row=row, column=1, value=col_name.replace("_", " ").title()).font = label_font
                ws_dash.cell(row=row, column=2, value=fmt_number(series.sum()))
                ws_dash.cell(row=row, column=3, value=fmt_number(series.mean()))
                ws_dash.cell(row=row, column=4, value=fmt_number(series.min()))
                ws_dash.cell(row=row, column=5, value=fmt_number(series.max()))
                for c in range(1, 6):
                    cell = ws_dash.cell(row=row, column=c)
                    cell.border = thin_border
                    cell.font = body_font
                    if i % 2 == 0:
                        cell.fill = zebra_fill
                row += 1
            row += 1

        # Section C — Categorical Column Breakdowns
        cat_cols = report_data.select_dtypes(include=["object", "string"]).columns.tolist()
        # Limit to columns with a sensible number of unique values, ignoring unhashable/array columns
        valid_cat_cols = []
        for c in cat_cols:
            try:
                if 1 < report_data[c].nunique() <= 30:
                    valid_cat_cols.append(c)
            except TypeError:
                pass
        cat_cols = valid_cat_cols
        if cat_cols and not report_data.empty:
            write_section_header(ws_dash, row, 1, "🔍  Categorical Breakdowns")
            row += 1
            for col_name in cat_cols:
                # mini sub-header for this category
                cat_header = ws_dash.cell(row=row, column=1, value=col_name.replace("_", " ").title())
                cat_header.font = Font(name="Segoe UI", size=10, bold=True, color="2E5090")
                count_header = ws_dash.cell(row=row, column=2, value="Row Count")
                count_header.font = header_font
                count_header.fill = accent_fill
                count_header.border = thin_border
                row += 1
                vc = report_data[col_name].value_counts(dropna=True)
                for i, (val, cnt) in enumerate(vc.items()):
                    ws_dash.cell(row=row, column=1, value=str(val)).border = thin_border
                    ws_dash.cell(row=row, column=2, value=int(cnt)).border = thin_border
                    if i % 2 == 0:
                        ws_dash.cell(row=row, column=1).fill = zebra_fill
                        ws_dash.cell(row=row, column=2).fill = zebra_fill
                    row += 1
                row += 1  # gap between categories

        # ── Sheet 3: Lineage Mapping ───────────────────────────────────────── #
        ws_lineage = wb.create_sheet(title="Lineage_Mapping")
        write_df_to_sheet(ws_lineage, "System Lineage Trace Mappings", lineage_data)

        # ── Sheet 4: PAS Mapping ───────────────────────────────────────────── #
        if pas_mapping is not None:
            ws_pas = wb.create_sheet(title="PAS_Mapping")
            write_df_to_sheet(ws_pas, "PAS Data Fields Mapping", pas_mapping)

        # ── Sheet 5: CRM Mapping ───────────────────────────────────────────── #
        if crm_mapping is not None:
            ws_crm = wb.create_sheet(title="CRM_Mapping")
            write_df_to_sheet(ws_crm, "CRM Data Fields Mapping", crm_mapping)

        # ── Sheet 6: Transformation Mapping ─────────────────────────────────── #
        if transformation_mapping is not None:
            ws_trans = wb.create_sheet(title="Transformation_Mapping")
            write_df_to_sheet(ws_trans, "Transformation Trace Mapping", transformation_mapping)

        # ── Sheet 7: Metadata ─────────────────────────────────────────────── #
        ws_meta = wb.create_sheet(title="Metadata")
        write_df_to_sheet(ws_meta, "Schema Catalog Metadata Dictionary", metadata)

        # ── Auto-width for all sheets ─────────────────────────────────────── #
        for sheet in wb.worksheets:
            for col in sheet.columns:
                try:
                    max_len = max(
                        [len(str(cell.value)) for cell in col if cell.value is not None] + [12]
                    )
                    sheet.column_dimensions[col[0].column_letter].width = min(max_len + 2, 55)
                except Exception:
                    pass

        import os
        final_filename = output_filename
        attempt = 1
        while True:
            try:
                wb.save(final_filename)
                print(f"[Excel Service] Report saved successfully as: {final_filename}")
                return final_filename
            except PermissionError:
                base, ext = os.path.splitext(output_filename)
                final_filename = f"{base}_{attempt}{ext}"
                attempt += 1
                if attempt > 100:
                    raise