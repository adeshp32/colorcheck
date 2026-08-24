from video_color_checker.ui import home_page


def test_generate_button_has_loading_state_and_no_gradient() -> None:
    page = home_page()

    assert 'class="submit" type="submit"' in page
    assert 'name="rights_confirmed" type="checkbox" required' in page
    assert 'submitButton.textContent = "Generating preview..."' in page
    assert 'submitButton.setAttribute("aria-busy", "true")' in page
    assert ".submit {" in page
    assert "background: transparent;" in page
    assert ".submit[aria-busy=\"true\"]" in page


def test_preview_uses_browser_compatible_mp4_source() -> None:
    report = {
        "summary": {
            "overall_score": 90,
            "recommendation": "Looks close.",
            "drift_level": "minimal",
            "reference_lighting": "neutral daylight",
            "target_lighting": "neutral daylight",
            "risky_frame_count": 0,
        },
        "guardrails": {"warnings": [], "clipping_risk_percent": 0},
        "correction": {
            "exposure_stops": 0,
            "contrast_multiplier": 1,
            "saturation_multiplier": 1,
        },
        "export_settings": {
            "correction_strength_percent": 50,
            "lighting_shift_threshold_percent": 60,
            "audio_status": "preserved",
        },
        "lighting_shift": {
            "shift_percent": 10,
            "threshold_percent": 60,
            "preserves_lighting_setup": True,
            "warnings": [],
        },
        "corrected_video_filename": "corrected_preview.mp4",
        "corrected_master_filename": "corrected_master.mov",
    }

    from video_color_checker.ui import job_page

    page = job_page("test-job", report)

    assert 'type="video/mp4"' in page
    assert "corrected_preview.mp4?codec=h264" in page
    assert "corrected_master.mov" in page
    assert "Quality-preserved master" in page
    assert "playsinline" in page
