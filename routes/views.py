from flask import Blueprint, render_template, abort
from config import Config
from services.room_manager import RoomManager

views_bp = Blueprint("views", __name__)
_room_mgr = RoomManager()

@views_bp.route("/")
@views_bp.route("/command-center")
def command_center():
    settings = _room_mgr.get_system_settings()
    return render_template(
        "command_center.html",
        active_page="command_center",
        settings=settings,
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/live-rooms")
@views_bp.route("/rooms")
def live_rooms():
    settings = _room_mgr.get_system_settings()
    return render_template(
        "live_rooms.html",
        active_page="live_rooms",
        settings=settings,
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/rooms/<room_id>")
def room_detail(room_id):
    room = _room_mgr.get_room_by_id(room_id)
    if not room:
        abort(404, description=f"Hostel room {room_id} not found.")
    return render_template(
        "room_detail.html",
        active_page="live_rooms",
        room=room,
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/investigation")
@views_bp.route("/detective")
def investigation():
    return render_template(
        "detective.html",
        active_page="investigation",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/nilm-simulator")
@views_bp.route("/simulator")
def nilm_simulator():
    return render_template(
        "nilm_simulator.html",
        active_page="nilm_simulator",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/trip-history")
@views_bp.route("/events")
def trip_history():
    return render_template(
        "trip_history.html",
        active_page="trip_history",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/sensors")
@views_bp.route("/hardware")
@views_bp.route("/esp32")
def hardware():
    return render_template(
        "hardware.html",
        active_page="sensors",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/reports")
def reports():
    return render_template(
        "reports.html",
        active_page="reports",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/settings")
def settings():
    current_settings = _room_mgr.get_system_settings()
    return render_template(
        "settings.html",
        active_page="settings",
        settings=current_settings,
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

# --------------------------------------------------------------------------
# Preserved Secondary Views
# --------------------------------------------------------------------------
@views_bp.route("/recommendations")
def recommendations():
    return render_template(
        "recommendations.html",
        active_page="recommendations",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/incidents")
def incidents():
    return render_template(
        "incidents.html",
        active_page="incidents",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/digital-twin")
def digital_twin():
    return render_template(
        "digital_twin.html",
        active_page="digital_twin",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/league")
def league():
    return render_template(
        "league.html",
        active_page="league",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )

@views_bp.route("/upload")
def upload():
    return render_template(
        "upload.html",
        active_page="upload",
        blocks=Config.HOSTEL_BLOCKS,
        disclaimer=Config.DISCLAIMER_TEXT
    )
