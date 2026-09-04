from colorcheck.web.pages import home_page


def test_home_keeps_analysis_form_focused() -> None:
    page = home_page(max_upload_mb=90, max_request_mb=95, max_video_seconds=60)

    assert "Color that isn't artificial." in page
    assert 'class="analysis-panel" aria-label="Upload analyzer"' in page
    assert 'class="panel analysis-panel"' not in page
    assert 'src="/assets/colorcheck-wordmark.svg" alt="colorcheck."' in page
    assert 'class="about-text about-story"' in page
    assert 'class="submit" type="submit"' in page
    assert 'name="rights_confirmed" type="checkbox" required' in page
    assert "Authorized media only." in page
    assert "Temporary uploads are deleted." in page
    assert "Run ColorCheck" in page
    assert "Match a target clip to a reference look." in page
    assert 'src="/assets/uploads.js" defer' in page
    assert 'src="/assets/analysis.js" defer' in page
    assert 'name="strength" type="hidden" value="100"' in page
    assert "Correction strength" not in page
    assert "Preserve selected area" not in page
    assert "Trim within selected area" not in page
    assert ".submit {" in page
    assert "background: transparent;" in page
    assert ".submit[aria-busy=\"true\"]" in page


def test_result_has_playable_editor_and_final_output_gate() -> None:
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

    from colorcheck.web.pages import job_page

    page = job_page("test-job", report)

    assert '<video controls playsinline preload="metadata" data-preview-video>' in page
    assert 'data-correction-strength aria-label="Mapped correction strength"' in page
    assert 'data-editor-panel="crop"' in page
    assert 'data-report-downloads hidden' in page
    assert "Report + corrected video" in page
    assert "Report only" in page
    assert "Corrected video only" in page
    assert "Color wheel" in page
    assert "Black &amp; white" in page
    assert "Prepare final output" in page
    assert "corrected video is never written to server storage" in page
