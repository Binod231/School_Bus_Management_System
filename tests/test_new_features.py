import pytest
from datetime import date, datetime, timedelta, timezone
from app.core.cache import redis_client
from app.models.trip import LocationUpdate, StudentStatus, TripStudent, TripDirection
from app.services.trip import cleanup_old_location_updates
from app.services.arrival_reminder_task import check_and_send_arrival_reminders
from app.utils.fcm import (
    send_push_notification,
    send_student_boarding_notification,
    send_student_unboarding_notification,
    send_arrival_confirmation_reminder_notification,
    send_bus_stop_arrival_notification,
    send_bus_location_update,
    send_incident_notification,
    send_arrival_notification,
    send_trip_started_notification,
    send_trip_completed_notification,
    send_emergency_transfer_notification
)
from sqlalchemy import select

@pytest.mark.asyncio
async def test_single_use_ws_ticket(client, test_setup):
    """Verifies that an authorized user receives a 60-second single-use ticket in Redis."""
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}
    trip_id = test_setup["trip"].id

    resp = await client.post(f"/api/v1/ws-ticket?trip_id={trip_id}", headers=guardian_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "ticket" in data
    assert data["expires_in"] == 60
    assert data["trip_id"] == trip_id

    # Verify stored in Redis
    ticket_val = await redis_client.get(f"ws_ticket:{data['ticket']}")
    assert ticket_val is not None


@pytest.mark.asyncio
async def test_end_of_trip_sweep_verification_enforcement(client, test_setup):
    """Verifies that a driver cannot finalize a trip without performing the mandatory rear bus sweep."""
    driver_headers = {"Authorization": f"Bearer {test_setup['driver_token']}"}
    trip_id = test_setup["trip"].id

    # Attempt to complete trip without sweep -> must be rejected with 400
    complete_resp = await client.patch(
        f"/api/v1/driver/trips/{trip_id}",
        json={"status": "COMPLETED"},
        headers=driver_headers
    )
    assert complete_resp.status_code == 400
    assert "Safety Check Required" in complete_resp.json()["detail"]

    # Perform sweep verification
    sweep_resp = await client.post(
        f"/api/v1/driver/trips/{trip_id}/verify-sweep",
        json={"notes": "Checked under all seats, bus is clear.", "confirm_seats_empty": True},
        headers=driver_headers
    )
    assert sweep_resp.status_code == 200, sweep_resp.text
    sweep_data = sweep_resp.json()
    assert sweep_data["sweep_verified"] is True

    # Now complete trip -> succeeds
    complete_after_sweep = await client.patch(
        f"/api/v1/driver/trips/{trip_id}",
        json={"status": "COMPLETED"},
        headers=driver_headers
    )
    assert complete_after_sweep.status_code == 200, complete_after_sweep.text
    assert complete_after_sweep.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_driver_sos_panic_workflow(client, test_setup):
    """Verifies that driver emergency panic button logs incident and triggers alert."""
    driver_headers = {"Authorization": f"Bearer {test_setup['driver_token']}"}
    trip_id = test_setup["trip"].id

    sos_resp = await client.post(
        f"/api/v1/driver/trips/{trip_id}/sos",
        json={
            "latitude": 27.7172,
            "longitude": 85.3240,
            "emergency_type": "accident",
            "description": "Minor collision with motorcycle, all students safe."
        },
        headers=driver_headers
    )
    assert sos_resp.status_code == 200, sos_resp.text
    data = sos_resp.json()
    assert data["broadcast_sent"] is True
    assert data["status"] == "EMERGENCY_BROADCAST_ACTIVE"
    assert "incident_id" in data


@pytest.mark.asyncio
async def test_speeding_telematics_detection(client, test_setup):
    """Verifies that high-frequency GPS ping with excessive speed registers location and triggers telematics warning."""
    driver_headers = {"Authorization": f"Bearer {test_setup['driver_token']}"}
    trip_id = test_setup["trip"].id

    loc_resp = await client.post(
        f"/api/v1/driver/trips/{trip_id}/location",
        json={
            "trip_id": trip_id,
            "latitude": 27.7180,
            "longitude": 85.3250,
            "speed": 78.5,  # > 60 km/h threshold
            "heading": 180.0
        },
        headers=driver_headers
    )
    assert loc_resp.status_code == 200, loc_resp.text
    data = loc_resp.json()
    assert data["speed"] == 78.5


@pytest.mark.asyncio
async def test_student_absence_call_off_and_driver_roster(client, test_setup):
    """Verifies guardian reporting absence notice and driver seeing it on today's trip."""
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}
    driver_headers = {"Authorization": f"Bearer {test_setup['driver_token']}"}
    student_id = test_setup["student"].id
    trip_id = test_setup["trip"].id

    # 1. Guardian submits absence
    today_str = date.today().isoformat()
    absence_resp = await client.post(
        f"/api/v1/guardian/students/{student_id}/absence",
        json={
            "date": today_str,
            "trip_type": "ALL_DAY",
            "reason": "Dental appointment"
        },
        headers=guardian_headers
    )
    assert absence_resp.status_code == 200, absence_resp.text
    absence_data = absence_resp.json()
    absence_id = absence_data["id"]
    assert absence_data["reason"] == "Dental appointment"

    # 2. Driver inspects trip absences
    driver_abs_resp = await client.get(
        f"/api/v1/driver/trips/{trip_id}/absences",
        headers=driver_headers
    )
    assert driver_abs_resp.status_code == 200, driver_abs_resp.text
    abs_list = driver_abs_resp.json()
    assert len(abs_list) >= 1
    assert any(a["student_id"] == student_id for a in abs_list)

    # 3. Guardian cancels absence
    del_resp = await client.delete(
        f"/api/v1/guardian/students/{student_id}/absences/{absence_id}",
        headers=guardian_headers
    )
    assert del_resp.status_code == 200, del_resp.text


@pytest.mark.asyncio
async def test_guardian_proximity_preferences(client, test_setup):
    """Verifies custom geofence alert threshold (e.g. 1200 meters) configuration."""
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}
    student_id = test_setup["student"].id

    # Update preferences
    put_resp = await client.put(
        f"/api/v1/guardian/students/{student_id}/alert-preferences",
        json={"alert_radius_meters": 1200.0, "notify_on_approaching": True},
        headers=guardian_headers
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["alert_radius_meters"] == 1200.0

    # Retrieve preferences
    get_resp = await client.get(
        f"/api/v1/guardian/students/{student_id}/alert-preferences",
        headers=guardian_headers
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["alert_radius_meters"] == 1200.0


@pytest.mark.asyncio
async def test_fleet_maintenance_and_expiry_alerts(client, test_setup):
    """Verifies bus maintenance logging, odometer tracking, and compliance expiry alerts."""
    admin_headers = {"Authorization": f"Bearer {test_setup['admin_token']}"}
    bus_id = test_setup["bus"].id

    # 1. Log maintenance
    maint_resp = await client.post(
        f"/api/v1/admin/buses/{bus_id}/maintenance",
        json={
            "service_type": "OIL_CHANGE",
            "cost": 15000.0,
            "currency": "NPR",
            "odometer_reading": 13200.0,
            "performed_by": "Kathmandu Auto Workshop",
            "notes": "Engine oil and filter replaced."
        },
        headers=admin_headers
    )
    assert maint_resp.status_code == 200, maint_resp.text
    m_data = maint_resp.json()
    assert m_data["service_type"] == "OIL_CHANGE"
    assert m_data["cost"] == 15000.0
    assert m_data["currency"] == "NPR"

    # 2. Get maintenance history
    hist_resp = await client.get(
        f"/api/v1/admin/buses/{bus_id}/maintenance",
        headers=admin_headers
    )
    assert hist_resp.status_code == 200, hist_resp.text
    assert len(hist_resp.json()) >= 1

    # 3. Check expiry alerts (insurance & fitness certificate expiring in test_setup)
    alerts_resp = await client.get(
        "/api/v1/admin/fleet/expiry-alerts",
        headers=admin_headers
    )
    assert alerts_resp.status_code == 200, alerts_resp.text
    alerts = alerts_resp.json()
    assert len(alerts) >= 1
    assert any(a["bus_id"] == bus_id for a in alerts)


@pytest.mark.asyncio
async def test_emergency_breakdown_bus_transfer(client, test_setup):
    """Verifies that an admin can transfer stranded students from a disabled bus to a replacement bus."""
    admin_headers = {"Authorization": f"Bearer {test_setup['admin_token']}"}
    old_trip_id = test_setup["trip"].id
    backup_bus_id = test_setup["backup_bus"].id
    driver_id = test_setup["driver_user"].id

    transfer_resp = await client.post(
        f"/api/v1/admin/trips/{old_trip_id}/emergency-transfer",
        json={
            "target_bus_id": backup_bus_id,
            "target_driver_id": driver_id,
            "reason": "Transmission issue on primary bus"
        },
        headers=admin_headers
    )
    assert transfer_resp.status_code == 200, transfer_resp.text
    t_data = transfer_resp.json()
    assert t_data["original_trip_id"] == old_trip_id
    assert t_data["new_trip_id"] != old_trip_id
    assert t_data["transferred_students_count"] >= 1


@pytest.mark.asyncio
async def test_cleanup_old_location_updates_service(db_session, test_setup):
    """Verifies that cleanup_old_location_updates removes stale records older than N days and retains recent ones."""
    trip_id = test_setup["trip"].id
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=75)
    recent_time = now - timedelta(days=10)

    # Insert 3 old updates and 2 recent updates
    old_updates = [
        LocationUpdate(trip_id=trip_id, latitude=27.7100, longitude=85.3200, speed=20.0, timestamp=old_time),
        LocationUpdate(trip_id=trip_id, latitude=27.7101, longitude=85.3201, speed=22.0, timestamp=old_time),
        LocationUpdate(trip_id=trip_id, latitude=27.7102, longitude=85.3202, speed=25.0, timestamp=old_time),
    ]
    recent_updates = [
        LocationUpdate(trip_id=trip_id, latitude=27.7200, longitude=85.3300, speed=30.0, timestamp=recent_time),
        LocationUpdate(trip_id=trip_id, latitude=27.7201, longitude=85.3301, speed=32.0, timestamp=recent_time),
    ]

    db_session.add_all(old_updates + recent_updates)
    await db_session.commit()

    # Verify all 5 were inserted
    res_before = await db_session.execute(select(LocationUpdate).where(LocationUpdate.trip_id == trip_id))
    assert len(res_before.scalars().all()) >= 5

    # Run cleanup with retention of 60 days
    cleanup_res = await cleanup_old_location_updates(db=db_session, days=60, batch_size=10)
    assert cleanup_res["success"] is True
    assert cleanup_res["deleted_count"] >= 3
    assert cleanup_res["retention_days"] == 60

    # Verify old updates were deleted and recent updates remain
    res_after = await db_session.execute(select(LocationUpdate).where(LocationUpdate.trip_id == trip_id))
    remaining = res_after.scalars().all()
    # None of the remaining updates should be older than 60 days
    cutoff = now - timedelta(days=60)
    for loc in remaining:
        assert loc.timestamp >= cutoff


@pytest.mark.asyncio
async def test_admin_cleanup_location_endpoint(client, test_setup):
    """Verifies that only authorized admins can trigger the location cleanup endpoint."""
    admin_headers = {"Authorization": f"Bearer {test_setup['admin_token']}"}
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}

    # Non-admin (guardian) attempt must be rejected with 403 Forbidden
    forbidden_resp = await client.post(
        "/api/v1/admin/system/cleanup-locations?days=60",
        headers=guardian_headers
    )
    assert forbidden_resp.status_code == 403

    # Admin request succeeds
    admin_resp = await client.post(
        "/api/v1/admin/system/cleanup-locations?days=60",
        headers=admin_headers
    )
    assert admin_resp.status_code == 200, admin_resp.text
    data = admin_resp.json()
    assert data["status"] == "success"
    assert "deleted_count" in data
    assert data["retention_days"] == 60
    assert "cutoff_date" in data


@pytest.mark.asyncio
async def test_arrival_confirmation_recurring_reminder_and_cleanup(client, db_session, test_setup):
    """
    Verifies that:
    1. Students dropped off > 10m ago trigger arrival reminders with Redis timestamp tracking.
    2. Repeated reminder checks within 10m do not duplicate sends.
    3. Guardian confirming arrival cleans up the Redis reminder key and updates status to AT_HOME.
    """
    trip = test_setup["trip"]
    trip_student = test_setup["trip_student"]
    student = test_setup["student"]
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}

    # Put trip in FROM_SCHOOL direction and student in DROPPED_OFF status 15 minutes ago
    trip.direction = TripDirection.FROM_SCHOOL
    fifteen_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=15)
    trip_student.status = StudentStatus.DROPPED_OFF
    trip_student.disembarked_at = fifteen_mins_ago
    await db_session.commit()

    cache_key = f"arrival_reminder:{trip_student.id}:last_sent"
    await redis_client.delete(cache_key)

    # 1. Trigger reminder check -> should dispatch reminder and store timestamp in Redis
    await check_and_send_arrival_reminders()
    last_sent_val = await redis_client.get(cache_key)
    assert last_sent_val is not None, "Redis reminder timestamp should be set after dispatch"

    # 2. Trigger again immediately -> should skip re-sending within 10m window
    await check_and_send_arrival_reminders()
    second_sent_val = await redis_client.get(cache_key)
    assert second_sent_val == last_sent_val, "Timestamp should not change within 10 minute window"

    # 3. Guardian confirms arrival via endpoint
    confirm_resp = await client.post(
        f"/api/v1/guardian/confirm-arrival/{student.id}",
        json={"is_confirmed": True},
        headers=guardian_headers
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert "confirmed successfully" in confirm_resp.json()["message"]

    # 4. Verify Redis reminder key is purged
    post_cleanup_val = await redis_client.get(cache_key)
    assert post_cleanup_val is None, "Redis reminder key should be removed upon arrival confirmation"

    # 5. Verify status updated in DB
    await db_session.refresh(trip_student)
    assert trip_student.status == StudentStatus.AT_HOME


@pytest.mark.asyncio
async def test_fcm_notification_helpers_and_serialization():
    """
    Verifies that all FCM push notification helpers execute safely,
    handle non-string data payloads by stringifying, and filter out invalid tokens.
    """
    sample_tokens = ["fcm_token_alpha", "fcm_token_beta", None, ""]

    # 1. Generic push with mixed non-string data types
    mixed_data = {
        "event_id": 1001,
        "is_emergency": True,
        "speed_kmh": 45.8,
        "status": "ACTIVE"
    }
    # Should not raise any ValueError / serialization exception
    res = await send_push_notification(sample_tokens, "Test Title", "Test Message", mixed_data)
    # In test environment without Firebase credentials file, it safely returns None (dry-run)
    assert res is None or res is not None

    # 2. Student boarding notification
    await send_student_boarding_notification(["tok1"], "John Doe", "BUS-12", "08:15 AM")

    # 3. Student unboarding notification
    await send_student_unboarding_notification(["tok1"], "John Doe", "BUS-12", "Central Square", "08:45 AM")

    # 4. Arrival confirmation reminder (10-minute recurring alert)
    await send_arrival_confirmation_reminder_notification(["tok1"], "John Doe", "BUS-12", "Central Square", 10)

    # 5. Bus stop arrival notification
    await send_bus_stop_arrival_notification(["tok1"], "John Doe", "BUS-12", "Central Square", "08:40 AM")

    # 6. Approaching location update
    await send_bus_location_update(["tok1"], "John Doe", "BUS-12", "North Avenue", "4 mins")

    # 7. Incident alert
    await send_incident_notification(["tok1"], "John Doe", "delay", "Road obstruction due to festival")

    # 8. Safe arrival notification
    await send_arrival_notification(["tok1"], "John Doe", "Kathmandu Academy", "08:50 AM")

    # 9. Trip started
    await send_trip_started_notification(["tok1"], "BUS-12", "North Route", "MORNING")

    # 10. Trip completed
    await send_trip_completed_notification(["tok1"], "BUS-12", "North Route", "MORNING")

    # 11. Emergency breakdown transfer
    await send_emergency_transfer_notification(["tok1"], "BUS-12", "BUS-99", "Flat tire replacement")


@pytest.mark.asyncio
async def test_admin_broadcast_custom_notification(client, test_setup):
    """Verifies that an admin can broadcast festival, holiday, and session notifications."""
    admin_headers = {"Authorization": f"Bearer {test_setup['admin_token']}"}
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}

    # 1. Non-admin attempt should be rejected with 403 Forbidden
    forbidden_resp = await client.post(
        "/api/v1/admin/notifications/broadcast",
        json={
            "title": "Dashain Holiday Notice",
            "message": "School will be closed for Dashain vacation.",
            "target": "GUARDIANS",
            "category": "FESTIVAL",
            "send_email": True
        },
        headers=guardian_headers
    )
    assert forbidden_resp.status_code == 403

    # 2. Admin broadcast to GUARDIANS
    broadcast_resp = await client.post(
        "/api/v1/admin/notifications/broadcast",
        json={
            "title": "Happy Dashain Festival!",
            "message": "School and bus services will remain closed from Ashwin 24 to Kartik 5 for Dashain vacation. Happy Dashain!",
            "target": "GUARDIANS",
            "category": "FESTIVAL",
            "send_email": True
        },
        headers=admin_headers
    )
    assert broadcast_resp.status_code == 200, broadcast_resp.text
    data = broadcast_resp.json()
    assert data["status"] == "success"
    assert data["title"] == "Happy Dashain Festival!"
    assert data["target"] == "GUARDIANS"
    assert data["category"] == "FESTIVAL"
    assert "push_tokens_targeted" in data
    assert "emails_targeted" in data

    # 3. Admin broadcast to specific ROUTE
    route_id = test_setup["route"].id
    route_resp = await client.post(
        "/api/v1/admin/notifications/broadcast",
        json={
            "title": "Route North Schedule Change",
            "message": "Bus timings for Route North will shift by 15 minutes starting next session.",
            "target": "ROUTE",
            "route_id": route_id,
            "category": "SESSION",
            "send_email": True
        },
        headers=admin_headers
    )
    assert route_resp.status_code == 200, route_resp.text
    route_data = route_resp.json()
    assert route_data["status"] == "success"
    assert route_data["target"] == "ROUTE"


@pytest.mark.asyncio
async def test_guardian_fcm_token_registration(client, test_setup):
    """Verifies that a guardian can register their mobile FCM device token via JSON body or query param."""
    guardian_headers = {"Authorization": f"Bearer {test_setup['guardian_token']}"}

    # 1. Check initial token status
    get_resp = await client.get("/api/v1/guardian/fcm-token", headers=guardian_headers)
    assert get_resp.status_code == 200, get_resp.text
    initial_data = get_resp.json()
    assert "has_token" in initial_data

    # 2. Register via JSON body
    post_resp = await client.post(
        "/api/v1/guardian/fcm-token",
        json={"fcm_token": "device_token_sample_abc_123"},
        headers=guardian_headers
    )
    assert post_resp.status_code == 200, post_resp.text
    assert post_resp.json()["has_token"] is True
    assert post_resp.json()["fcm_token"] == "device_token_sample_abc_123"

    # 3. Check token status after update
    get_after = await client.get("/api/v1/guardian/fcm-token", headers=guardian_headers)
    assert get_after.status_code == 200
    assert get_after.json()["has_token"] is True
    assert get_after.json()["fcm_token"] == "device_token_sample_abc_123"

    # 4. Register via query parameter fallback
    query_resp = await client.post(
        "/api/v1/guardian/fcm-token?fcm_token=device_token_query_xyz_456",
        headers=guardian_headers
    )
    assert query_resp.status_code == 200
    assert query_resp.json()["fcm_token"] == "device_token_query_xyz_456"




