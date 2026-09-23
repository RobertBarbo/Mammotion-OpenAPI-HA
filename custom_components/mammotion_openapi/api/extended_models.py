"""Models for additional read-only endpoints in Mammotion's public OpenAPI spec.

These schemas are documented at https://api-open.mammotion.com/api-docs but
have not yet been verified against a mower. Optional fields remain nullable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, TypeVar

from .exceptions import MammotionMalformedResponseError
from .models import _mapping, _optional_bool, _optional_int, _optional_string


@dataclass(frozen=True, slots=True)
class WorkParameters:
    """Documented current mower work parameters, without inferred units."""

    command_result: bool | None = None
    result_message: str | None = None
    edge_mode: int | None = None
    ride_boundary_distance: float | None = None
    channel_mode: int | None = None
    job_content: int | None = None
    dump_period_sqm: int | None = None
    knife_height: int | None = None
    speed: int | None = None
    channel_width: int | None = None
    toward: int | None = None
    toward_mode: int | None = None
    toward_included_angle: int | None = None
    ultra_wave: int | None = None
    boundary_zigzag_order: int | None = None
    forbidden_area_circle_times: int | None = None


@dataclass(frozen=True, slots=True)
class WorkReport:
    """One documented item in paginated mowing history."""

    work_id: str | None = None
    end_work_time: int | None = None  # Unix milliseconds, not seconds.
    work_type: int | None = None
    work_result: int | None = None
    work_progress: float | None = None
    work_area: float | None = None
    work_time_used: int | None = None  # Seconds.


@dataclass(frozen=True, slots=True)
class WorkReportPage:
    records: tuple[WorkReport, ...] = ()
    total: int | None = None
    page_number: int | None = None
    page_size: int | None = None
    pages: int | None = None


@dataclass(frozen=True, slots=True)
class WorkReportSummary:
    save_time: float | None = None  # Minutes.
    carbon_reduction: float | None = None  # Grams.
    work_count: int | None = None
    total_work_area: float | None = None  # Square metres.


@dataclass(frozen=True, slots=True)
class WorkProcessEvent:
    time_stamp: int | None = None  # Unix milliseconds.
    event_code: int | None = None


@dataclass(frozen=True, slots=True)
class WorkReportDetail:
    work_area: float | None = None
    work_time_used: int | None = None
    save_time: float | None = None
    carbon_reduction: float | None = None
    energy_consume: float | None = None
    start_work_time: int | None = None
    end_work_time: int | None = None
    work_type: int | None = None
    job_content: int | None = None
    work_process: tuple[WorkProcessEvent, ...] = ()
    work_param: WorkParameters | None = None
    # Signed mapFilePath is deliberately not retained.


@dataclass(frozen=True, slots=True)
class DeviceErrorCode:
    code: int | None = None
    implication: str | None = None
    solution: str | None = None
    gmt_create: int | None = None  # Unix milliseconds.
    create_time: int | None = None  # Unix milliseconds.
    fault_level: int | None = None
    priority: int | None = None
    # Documented image/video/button resources are deliberately not retained.


@dataclass(frozen=True, slots=True)
class DeviceErrorCodePage:
    records: tuple[DeviceErrorCode, ...] = ()
    total: int | None = None
    page_number: int | None = None
    page_size: int | None = None
    has_more: bool | None = None


def parse_work_parameters(value: object) -> WorkParameters:
    data = _mapping(value, "work parameters")
    kind = "work parameters"
    return WorkParameters(
        command_result=_optional_bool(data, "commandResult", kind),
        result_message=_optional_string(data, "resultMessage", kind),
        edge_mode=_optional_int(data, "edgeMode", kind),
        ride_boundary_distance=_optional_number(data, "rideBoundaryDistance", kind),
        channel_mode=_optional_int(data, "channelMode", kind),
        job_content=_optional_int(data, "jobContent", kind),
        dump_period_sqm=_optional_int(data, "dumpPeriodSqm", kind),
        knife_height=_optional_int(data, "knifeHeight", kind),
        speed=_optional_int(data, "speed", kind),
        channel_width=_optional_int(data, "channelWidth", kind),
        toward=_optional_int(data, "toward", kind),
        toward_mode=_optional_int(data, "towardMode", kind),
        toward_included_angle=_optional_int(data, "towardIncludedAngle", kind),
        ultra_wave=_optional_int(data, "ultraWave", kind),
        boundary_zigzag_order=_optional_int(data, "boundaryZigzagOrder", kind),
        forbidden_area_circle_times=_optional_int(data, "forbiddenAreaCircleTimes", kind),
    )


def parse_work_report_page(value: object) -> WorkReportPage:
    data = _mapping(value, "work report page")
    kind = "work report page"
    return WorkReportPage(
        records=_optional_array(data, "records", parse_work_report, kind),
        total=_optional_int(data, "total", kind),
        page_number=_optional_int(data, "pageNumber", kind),
        page_size=_optional_int(data, "pageSize", kind),
        pages=_optional_int(data, "pages", kind),
    )


def parse_work_report(value: object) -> WorkReport:
    data = _mapping(value, "work report")
    kind = "work report"
    return WorkReport(
        work_id=_optional_string(data, "workId", kind),
        end_work_time=_optional_int(data, "endWorkTime", kind),
        work_type=_optional_int(data, "workType", kind),
        work_result=_optional_int(data, "workResult", kind),
        work_progress=_optional_number(data, "workProgress", kind),
        work_area=_optional_number(data, "workArea", kind),
        work_time_used=_optional_int(data, "workTimeUsed", kind),
    )


def parse_work_report_summary(value: object) -> WorkReportSummary:
    data = _mapping(value, "work report summary")
    kind = "work report summary"
    return WorkReportSummary(
        save_time=_optional_number(data, "saveTime", kind),
        carbon_reduction=_optional_number(data, "carbonReduction", kind),
        work_count=_optional_int(data, "workCount", kind),
        total_work_area=_optional_number(data, "totalWorkArea", kind),
    )


def parse_work_report_detail(value: object) -> WorkReportDetail:
    data = _mapping(value, "work report detail")
    kind = "work report detail"
    parameters = data.get("workParam")
    return WorkReportDetail(
        work_area=_optional_number(data, "workArea", kind),
        work_time_used=_optional_int(data, "workTimeUsed", kind),
        save_time=_optional_number(data, "saveTime", kind),
        carbon_reduction=_optional_number(data, "carbonReduction", kind),
        energy_consume=_optional_number(data, "energyConsume", kind),
        start_work_time=_optional_int(data, "startWorkTime", kind),
        end_work_time=_optional_int(data, "endWorkTime", kind),
        work_type=_optional_int(data, "workType", kind),
        job_content=_optional_int(data, "jobContent", kind),
        work_process=_optional_array(data, "workProcess", _parse_work_process, kind),
        work_param=parse_work_parameters(parameters) if parameters is not None else None,
    )


def _parse_work_process(value: object) -> WorkProcessEvent:
    data = _mapping(value, "work process event")
    return WorkProcessEvent(
        time_stamp=_optional_int(data, "timeStamp", "work process event"),
        event_code=_optional_int(data, "eventCode", "work process event"),
    )


def parse_error_code_page(value: object) -> DeviceErrorCodePage:
    data = _mapping(value, "error code page")
    kind = "error code page"
    return DeviceErrorCodePage(
        records=_optional_array(data, "records", _parse_error_code, kind),
        total=_optional_int(data, "total", kind),
        page_number=_optional_int(data, "pageNumber", kind),
        page_size=_optional_int(data, "pageSize", kind),
        has_more=_optional_bool(data, "hasMore", kind),
    )


def _parse_error_code(value: object) -> DeviceErrorCode:
    data = _mapping(value, "error code")
    kind = "error code"
    return DeviceErrorCode(
        code=_optional_int(data, "code", kind),
        implication=_optional_string(data, "implication", kind),
        solution=_optional_string(data, "solution", kind),
        gmt_create=_optional_int(data, "gmtCreate", kind),
        create_time=_optional_int(data, "createTime", kind),
        fault_level=_optional_int(data, "faultLevel", kind),
        priority=_optional_int(data, "priority", kind),
    )


def _optional_number(data: Mapping[str, Any], key: str, kind: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MammotionMalformedResponseError(f"Expected {kind}.{key} to be a number or null")
    return float(value)


_T = TypeVar("_T")


def _optional_array(
    data: Mapping[str, Any], key: str, parse_item: Callable[[object], _T], kind: str
) -> tuple[_T, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise MammotionMalformedResponseError(f"Expected {kind}.{key} to be a list or null")
    return tuple(parse_item(item) for item in value)
