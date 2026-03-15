"""
DaOnRoad - Excel Export
Sheet1: Bus Summary / Sheet2: Route Detail / Sheet3: Passenger
"""
import io
from typing import List, Dict, Any, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BUS_COLORS = [
    "4472C4","ED7D31","70AD47","FF0000","7030A0",
    "00B0F0","FFC000","92D050","00B050","FF7F50"
]
HEADER_FILL = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
ALT_FILL    = PatternFill(start_color="EEF3FF", end_color="EEF3FF", fill_type="solid")

def _border():
    s = Side(style='thin', color="BBBBBB")
    return Border(left=s, right=s, top=s, bottom=s)

def _hcenter(cell):
    cell.alignment = Alignment(horizontal="center", vertical="center")

def _set_col_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


class ExcelExporter:
    def export(self, routes: List[Dict], destination: Dict,
               summary: Optional[Dict] = None) -> bytes:
        wb = Workbook()
        self._summary_sheet(wb, routes, destination, summary)
        self._route_sheet(wb, routes, destination)
        self._passenger_sheet(wb, routes)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ── Sheet 1: Bus Summary ─────────────────────────────────
    def _summary_sheet(self, wb, routes, destination, summary):
        ws = wb.active
        ws.title = "Bus Summary"
        ws.row_dimensions[1].height = 28

        ws.merge_cells("A1:G1")
        ws["A1"] = "🚌  DaOnRoad — 버스 노선 최적화 결과"
        ws["A1"].font = Font(size=15, bold=True, color="1F3864")
        ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

        ws.merge_cells("A2:G2")
        ws["A2"] = (f"도착지: {destination.get('address','')}   "
                    f"|   도착 목표: {destination.get('arrival_time','')}")
        ws["A2"].font = Font(size=10, italic=True, color="595959")
        _hcenter(ws["A2"])

        if summary:
            ws.merge_cells("A3:G3")
            ws["A3"] = (f"총 승객 {summary.get('total_passengers',0)}명  |  "
                        f"버스 {summary.get('total_buses',0)}대")
            ws["A3"].font = Font(size=10, color="595959")
            _hcenter(ws["A3"])

        ws.append([])

        hdrs = ["버스ID","출발지","도착지","출발시간","도착시간","소요(분)","탑승인원"]
        ws.append(hdrs)
        hr = ws.max_row
        for c in range(1, len(hdrs)+1):
            cell = ws.cell(hr, c)
            cell.fill = HEADER_FILL; cell.font = HEADER_FONT
            _hcenter(cell); cell.border = _border()

        for i, route in enumerate(routes):
            v   = route.get('vehicle', {})
            row = [
                route.get('bus_id',''),
                v.get('start_location',''),
                destination.get('address',''),
                route.get('departure_time',''),
                route.get('arrival_time',''),
                route.get('total_duration_min', 0),
                route.get('total_passengers', 0),
            ]
            ws.append(row)
            dr = ws.max_row
            bc = BUS_COLORS[i % len(BUS_COLORS)]
            for c in range(1, len(row)+1):
                cell = ws.cell(dr, c)
                _hcenter(cell); cell.border = _border()
                if c == 1:
                    cell.fill = PatternFill(start_color=bc, end_color=bc, fill_type="solid")
                    cell.font = Font(color="FFFFFF", bold=True)
                elif i % 2 == 1:
                    cell.fill = ALT_FILL

        _set_col_widths(ws, [12,22,28,12,12,10,12])

    # ── Sheet 2: Route Detail ────────────────────────────────
    def _route_sheet(self, wb, routes, destination):
        ws = wb.create_sheet("Route Detail")

        hdrs = ["버스ID","픽업순서","이름","탑승주소","탑승시간","탑승인원","비고"]
        ws.append(hdrs)
        hr = ws.max_row
        for c in range(1, len(hdrs)+1):
            cell = ws.cell(hr, c)
            cell.fill = HEADER_FILL; cell.font = HEADER_FONT
            _hcenter(cell); cell.border = _border()

        for i, route in enumerate(routes):
            bc = BUS_COLORS[i % len(BUS_COLORS)]
            pickup_seq = 0

            for stop in route.get('stops', []):
                stype = stop.get('type','')
                if stype not in ('pickup', 'destination'):
                    continue

                if stype == 'pickup':
                    pickup_seq += 1
                    row = [
                        route.get('bus_id',''),
                        pickup_seq,
                        stop.get('name',''),
                        stop.get('address',''),
                        stop.get('pickup_time',''),
                        stop.get('passenger_count', 0),
                        "탑승",
                    ]
                else:  # destination
                    row = [
                        route.get('bus_id',''),
                        "",
                        "▶ 도착지",
                        destination.get('address', stop.get('address','')),
                        stop.get('pickup_time', route.get('arrival_time','')),
                        "",
                        "도착",
                    ]

                ws.append(row)
                dr = ws.max_row
                for c in range(1, len(row)+1):
                    cell = ws.cell(dr, c)
                    _hcenter(cell); cell.border = _border()
                    if c == 1:
                        cell.fill = PatternFill(start_color=bc, end_color=bc, fill_type="solid")
                        cell.font = Font(color="FFFFFF", bold=True)
                    elif stype == 'destination':
                        cell.fill = PatternFill(start_color="FFE0E0", end_color="FFE0E0", fill_type="solid")
                    elif dr % 2 == 0:
                        cell.fill = ALT_FILL

        _set_col_widths(ws, [12, 10, 18, 35, 12, 10, 8])

    # ── Sheet 3: Passenger ───────────────────────────────────
    def _passenger_sheet(self, wb, routes):
        ws = wb.create_sheet("Passenger")

        hdrs = ["이름","버스ID","탑승주소","탑승시간","탑승인원"]
        ws.append(hdrs)
        hr = ws.max_row
        for c in range(1, len(hdrs)+1):
            cell = ws.cell(hr, c)
            cell.fill = HEADER_FILL; cell.font = HEADER_FONT
            _hcenter(cell); cell.border = _border()

        for i, route in enumerate(routes):
            bc = BUS_COLORS[i % len(BUS_COLORS)]
            for stop in route.get('stops', []):
                if stop.get('type') != 'pickup':
                    continue
                row = [
                    stop.get('name',''),
                    route.get('bus_id',''),
                    stop.get('address',''),
                    stop.get('pickup_time',''),
                    stop.get('passenger_count', 1),
                ]
                ws.append(row)
                dr = ws.max_row
                for c in range(1, len(row)+1):
                    cell = ws.cell(dr, c)
                    _hcenter(cell); cell.border = _border()
                    if c == 2:
                        cell.fill = PatternFill(start_color=bc, end_color=bc, fill_type="solid")
                        cell.font = Font(color="FFFFFF", bold=True)
                    elif dr % 2 == 0:
                        cell.fill = ALT_FILL

        _set_col_widths(ws, [20, 12, 38, 12, 10])
