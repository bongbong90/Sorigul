# Legacy Repository Inventory — 5F evidence appendix

Companion to [`STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29.md`](STUDY_USE_FULL_SOURCE_CONTRACT_REGRESSION_2026-09-29.md) (#123).

- Legacy baseline: `bongbong90/jeonsa_doumi@fbc86313a179a62a586386551f99384a9fce5fc8` (read-only clone outside the Sorigul repo; nothing copied or imported)
- Tracked files enumerated: **337** (`git ls-files`)
- Classification: ACTIVE 58, ARCHIVED 26, DEPRECATED 30, EXPERIMENTAL 22, SUPPORTING 201
- Category: Colab 4, Google Drive 8, Local transcription 2, UI/runtime 46, active docs 25, archived/backup/POC/experimental 36, config/settings 43, filename/file handling 6, notebooks 1, persistence/recovery 5, test/probe/validation 161

Method: every path was classified by call-graph evidence (imports/`connect()` wiring in `gui_main.py`, `auto_transcribe.py`, and the Tauri `backend/main.py` routers), not by filename alone. Binary assets are listed but have no behaviour. UNKNOWN candidates were investigated until resolved; the Phase 2 backup service resolved to a no-op stub (EXPERIMENTAL).

| # | Path | Category | Classification | Evidence / note |
|---|---|---|---|---|
| 1 | `.gitignore` | config/settings | SUPPORTING | build/dev config |
| 2 | `PROJECT_CONTEXT.md` | active docs | SUPPORTING | current-state docs at baseline (evidence, not authority) |
| 3 | `README.md` | active docs | SUPPORTING | current-state docs at baseline (evidence, not authority) |
| 4 | `RELEASE_NOTES.md` | active docs | SUPPORTING | current-state docs at baseline (evidence, not authority) |
| 5 | `archive/icon_tests/icon_16.png` | archived/backup/POC/experimental | ARCHIVED | superseded backup / icon POC |
| 6 | `archive/icon_tests/icon_24.png` | archived/backup/POC/experimental | ARCHIVED | superseded backup / icon POC |
| 7 | `archive/icon_tests/icon_32.png` | archived/backup/POC/experimental | ARCHIVED | superseded backup / icon POC |
| 8 | `archive/icon_tests/transcribe_helper_regenerated.ico` | archived/backup/POC/experimental | ARCHIVED | superseded backup / icon POC |
| 9 | `archive/old_backups/gui_main.backup_texttest_20260414_143239.py` | archived/backup/POC/experimental | ARCHIVED | superseded backup / icon POC |
| 10 | `assets/fonts/GmarketSansTTFBold.ttf` | UI/runtime | SUPPORTING | icons/fonts |
| 11 | `assets/fonts/GmarketSansTTFLight.ttf` | UI/runtime | SUPPORTING | icons/fonts |
| 12 | `assets/fonts/GmarketSansTTFMedium.ttf` | UI/runtime | SUPPORTING | icons/fonts |
| 13 | `assets/transcribe_helper.ico` | UI/runtime | SUPPORTING | icons/fonts |
| 14 | `assets/transcribe_helper.png` | UI/runtime | SUPPORTING | icons/fonts |
| 15 | `assets/transcribe_helper.svg` | UI/runtime | SUPPORTING | icons/fonts |
| 16 | `auto_transcribe.py` | Local transcription | ACTIVE | Local Whisper worker: medium, CUDA/CPU, fp16 auto/fallback, locked decoding, session state, stop.flag |
| 17 | `backend/__init__.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 18 | `backend/api/__init__.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 19 | `backend/api/routes_backup.py` | archived/backup/POC/experimental | EXPERIMENTAL | Phase 2 no-op backup stub (copies nothing); no user capability |
| 20 | `backend/api/routes_engines.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 21 | `backend/api/routes_files.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 22 | `backend/api/routes_health.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 23 | `backend/api/routes_jobs.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 24 | `backend/api/routes_settings.py` | config/settings | ACTIVE | Tauri backend settings |
| 25 | `backend/main.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 26 | `backend/models/__init__.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 27 | `backend/models/engine.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 28 | `backend/models/file_item.py` | filename/file handling | ACTIVE | Tauri backend folder scan / paths |
| 29 | `backend/models/job.py` | persistence/recovery | ACTIVE | Tauri backend Job model/persistence/runner |
| 30 | `backend/models/progress.py` | persistence/recovery | ACTIVE | Tauri backend Job model/persistence/runner |
| 31 | `backend/models/settings.py` | config/settings | ACTIVE | Tauri backend settings |
| 32 | `backend/services/__init__.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 33 | `backend/services/audio_chunker.py` | Colab | EXPERIMENTAL | installed Tauri Direct Colab path (prior audit NA-003); behaviour mirrors PySide Colab contract |
| 34 | `backend/services/backup_service.py` | archived/backup/POC/experimental | EXPERIMENTAL | Phase 2 no-op backup stub (copies nothing); no user capability |
| 35 | `backend/services/colab_cli_service.py` | Colab | EXPERIMENTAL | Phase 12 WSL Colab CLI research |
| 36 | `backend/services/colab_http_service.py` | Colab | EXPERIMENTAL | installed Tauri Direct Colab path (prior audit NA-003); behaviour mirrors PySide Colab contract |
| 37 | `backend/services/colab_result_merger.py` | Colab | EXPERIMENTAL | installed Tauri Direct Colab path (prior audit NA-003); behaviour mirrors PySide Colab contract |
| 38 | `backend/services/engine_adapter.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 39 | `backend/services/file_service.py` | filename/file handling | ACTIVE | Tauri backend folder scan / paths |
| 40 | `backend/services/filename_service.py` | filename/file handling | EXPERIMENTAL | preview/apply stub (prior audit NA-002) |
| 41 | `backend/services/google_drive_upload_service.py` | Google Drive | ACTIVE | Phase 23D Drive bundle upload (installed Tauri) |
| 42 | `backend/services/job_runner.py` | persistence/recovery | ACTIVE | Tauri backend Job model/persistence/runner |
| 43 | `backend/services/job_service.py` | persistence/recovery | ACTIVE | Tauri backend Job model/persistence/runner |
| 44 | `backend/services/legacy_drive_queue_service.py` | Google Drive | DEPRECATED | Drive Queue guard stub |
| 45 | `backend/services/local_whisper_service.py` | Local transcription | ACTIVE | Phase 21-23 Local Whisper adapter (installed Tauri) |
| 46 | `backend/services/mock_engine_adapter.py` | test/probe/validation | SUPPORTING | mock engine for probes |
| 47 | `backend/sidecar_main.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 48 | `backend/storage/__init__.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 49 | `backend/storage/backup_manifest_store.py` | archived/backup/POC/experimental | EXPERIMENTAL | Phase 2 no-op backup stub (copies nothing); no user capability |
| 50 | `backend/storage/jobs_store.py` | persistence/recovery | ACTIVE | Tauri backend Job model/persistence/runner |
| 51 | `backend/storage/settings_store.py` | config/settings | ACTIVE | Tauri backend settings |
| 52 | `backend/tauri_backend_sidecar.spec` | config/settings | SUPPORTING | Tauri backend sidecar build |
| 53 | `backend/utils/__init__.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 54 | `backend/utils/event_utils.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 55 | `backend/utils/path_resolver.py` | filename/file handling | ACTIVE | Tauri backend folder scan / paths |
| 56 | `backend/utils/path_utils.py` | filename/file handling | ACTIVE | Tauri backend folder scan / paths |
| 57 | `backend/utils/process_utils.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 58 | `backend/utils/srt_utils.py` | UI/runtime | ACTIVE | Tauri FastAPI backend (Phase 23 MSI) |
| 59 | `colab_drive_worker.py` | Google Drive | DEPRECATED | Drive Queue path (contract §6 exclusion); lazily imported only by the deprecated Queue UI |
| 60 | `colab_transcribe.ipynb` | notebooks | ACTIVE | Colab faster-whisper large-v3 Flask server, float16/int8, ko, beam 5 |
| 61 | `docs/architecture/current_system_map.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 62 | `docs/architecture/phase2_backend_skeleton.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 63 | `docs/architecture/phase3_local_job_queue.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 64 | `docs/architecture/phase4_job_runner_adapter.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 65 | `docs/architecture/phase5_direct_colab_http_adapter.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 66 | `docs/architecture/refactor_boundaries.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 67 | `docs/architecture/transcription_flow_as_is.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 68 | `docs/colab_drive_queue_design.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 69 | `docs/colab_large_v3_workflow.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 70 | `docs/colab_long_transcription_validation.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 71 | `docs/current_feature_inventory.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 72 | `docs/design/DESIGN1.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 73 | `docs/design/DESIGN2.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 74 | `docs/design/README.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 75 | `docs/design/Transcription Assistant.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 76 | `docs/design/code.html` | active docs | SUPPORTING | design/inventory/flow docs |
| 77 | `docs/design/reference_app_icon.png` | active docs | SUPPORTING | design/inventory/flow docs |
| 78 | `docs/design/reference_main_ui.png` | active docs | SUPPORTING | design/inventory/flow docs |
| 79 | `docs/design/reference_tray_notification.png` | active docs | SUPPORTING | design/inventory/flow docs |
| 80 | `docs/drive_queue_google_api_integration_plan.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 81 | `docs/drive_queue_phase_i_summary_and_j_plan.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 82 | `docs/drive_queue_phase_j0_scope_lock.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 83 | `docs/drive_queue_phase_j10_worker_job_id_safety.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 84 | `docs/drive_queue_phase_j1_auth_probe.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 85 | `docs/drive_queue_phase_j2_root_folder.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 86 | `docs/drive_queue_phase_j3_metadata.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 87 | `docs/drive_queue_phase_j4_files.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 88 | `docs/drive_queue_phase_j5a_gui_submission.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 89 | `docs/drive_queue_phase_j5b_gui_polling.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 90 | `docs/drive_queue_phase_j5c_gui_output_sync.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 91 | `docs/drive_queue_phase_j6_worker_drive_e2e.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 92 | `docs/drive_queue_phase_j7_upload_isolation.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 93 | `docs/drive_queue_phase_j8_qa_checklist.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 94 | `docs/drive_queue_phase_j9_real_whisper_worker.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 95 | `docs/final_release_checklist.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 96 | `docs/google_drive_upload_design.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 97 | `docs/gui_drive_queue_integration_plan.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 98 | `docs/logs/.gitkeep` | active docs | SUPPORTING | design/inventory/flow docs |
| 99 | `docs/progress_bar_smooth_1_to_100.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 100 | `docs/progress_smoothing_design.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 101 | `docs/project/jeonsa_doumi_dev_summary_detail.pdf` | active docs | SUPPORTING | design/inventory/flow docs |
| 102 | `docs/project/jeonsa_doumi_dev_summary_short.pdf` | active docs | SUPPORTING | design/inventory/flow docs |
| 103 | `docs/project_docs_update_report_20260527.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 104 | `docs/recent_development_history.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 105 | `docs/requests/.gitkeep` | active docs | SUPPORTING | design/inventory/flow docs |
| 106 | `docs/research/phase12_closeout_phase13_readiness.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 107 | `docs/research/phase12a_colab_cli_wsl2_poc.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 108 | `docs/research/phase12b_wsl2_colab_cli_setup.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 109 | `docs/research/phase12c_colab_cli_auth_path_preflight.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 110 | `docs/research/phase12d_colab_cli_oauth_safety_plan.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 111 | `docs/research/phase12e_colab_cli_oauth_only_feasibility.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 112 | `docs/research/phase12f_cpu_runtime_smoke_gate.md` | archived/backup/POC/experimental | EXPERIMENTAL | Colab CLI research |
| 113 | `docs/research/phase13a_tauri_react_transition_design.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 114 | `docs/research/phase13b_env_supplemental_diagnosis.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 115 | `docs/research/phase13b_tauri_dev_env_survey.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 116 | `docs/research/phase13c_frontend_tauri_scaffold_poc.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 117 | `docs/research/phase13d_react_screen_skeleton_poc.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 118 | `docs/research/phase13e_fastapi_backend_connection_poc.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 119 | `docs/research/phase14_tauri_backend_launcher_closeout.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 120 | `docs/research/phase14a_tauri_backend_launcher_design.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 121 | `docs/research/phase14b_tauri_backend_launcher_command_stub.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 122 | `docs/research/phase14c_fastapi_backend_launcher_start_stop_poc.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 123 | `docs/research/phase15_tauri_execution_validation_closeout.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 124 | `docs/research/phase15a_frontend_dependency_install_build_preflight.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 125 | `docs/research/phase15b_rust_tauri_compile_check_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 126 | `docs/research/phase15c1_tauri_dev_window_launch_poc.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 127 | `docs/research/phase15c2_backend_launcher_start_stop_poc.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 128 | `docs/research/phase15e1_tauri_ui_design_source_application.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 129 | `docs/research/phase15e2_icon_tray_notification_design_review.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 130 | `docs/research/phase15e_tauri_ui_design_application_closeout.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 131 | `docs/research/phase16_gdrive_queue_legacy_closeout.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 132 | `docs/research/phase16a_gdrive_queue_legacy_inventory.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 133 | `docs/research/phase16b_gdrive_queue_legacy_docs_cleanup.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 134 | `docs/research/phase16c_gdrive_queue_legacy_guard.md` | archived/backup/POC/experimental | ARCHIVED | Drive Queue design/phase docs |
| 135 | `docs/research/phase17a_tauri_actual_job_flow_gap_analysis.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 136 | `docs/research/phase18a_tauri_frontend_job_client.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 137 | `docs/research/phase18b_tauri_ui_job_flow_wiring.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 138 | `docs/research/phase18c2_tauri_job_flow_missing_fields_fix.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 139 | `docs/research/phase18c3_tauri_actual_job_flow_final_acceptance.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 140 | `docs/research/phase18c_tauri_actual_job_flow_wiring_acceptance.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 141 | `docs/research/phase19a2_tauri_backend_launcher_runtime_verification.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 142 | `docs/research/phase19a_tauri_runtime_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 143 | `docs/research/phase20a_tauri_job_create_smoke_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 144 | `docs/research/phase20b_tauri_ui_job_create_smoke.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 145 | `docs/research/phase20c_tauri_job_start_status_transition_smoke.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 146 | `docs/research/phase21a_local_whisper_backend_adapter_wiring.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 147 | `docs/research/phase21b_local_whisper_real_mp3_smoke.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 148 | `docs/research/phase21c_tauri_ui_local_whisper_real_mp3_smoke.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 149 | `docs/research/phase22a_clean_build_release_decision.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 150 | `docs/research/phase22b_msi_only_clean_packaging_recovery.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 151 | `docs/research/phase23a_tauri_local_whisper_output_bundle_contract.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 152 | `docs/research/phase23b_installed_tauri_backend_runtime.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 153 | `docs/research/phase23c_installed_tauri_local_whisper_output_bundle_smoke.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 154 | `docs/research/phase23d1_google_drive_bundle_upload_contract_audit.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 155 | `docs/research/phase23d2_drive_bundle_upload_offline_implementation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 156 | `docs/research/phase23d3a_installed_drive_packaging_readiness.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 157 | `docs/research/phase23d3b1_installed_frontend_dialog_ipc_blocker.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 158 | `docs/research/phase23d3b2_unicode_job_creation_contract.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 159 | `docs/research/phase23d3b3_drive_frozen_runtime_packaging.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 160 | `docs/research/phase23d3b5_drive_job_projection_and_persistence.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 161 | `docs/research/phase23d3c_installed_drive_upload_final.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 162 | `docs/research/phase23e_msi_release_closeout_final.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 163 | `docs/session_and_stop_flow.md` | active docs | SUPPORTING | design/inventory/flow docs |
| 164 | `docs/validation/phase10_5_colab_http_ui_progress_hotfix.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 165 | `docs/validation/phase10_gdrive_direct_result_upload.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 166 | `docs/validation/phase11_colab_ui_simplification.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 167 | `docs/validation/phase6a_real_colab_single_file_test.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 168 | `docs/validation/phase6b_colab_http_chunk_merge_resume.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 169 | `docs/validation/phase6c_real_long_colab_chunk_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 170 | `docs/validation/phase7a_colab_http_chunk_ui_options.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 171 | `docs/validation/phase7b_gui_colab_http_job_runner.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 172 | `docs/validation/phase7c_gui_long_colab_http_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 173 | `docs/validation/phase7d_pyside_ui_cleanup.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 174 | `docs/validation/phase8_full_source_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 175 | `docs/validation/phase9_pyside_clean_build_validation.md` | test/probe/validation | SUPPORTING | phase validation/design record |
| 176 | `drive_queue_backend.py` | Google Drive | DEPRECATED | Drive Queue path (contract §6 exclusion); lazily imported only by the deprecated Queue UI |
| 177 | `drive_queue_manager.py` | Google Drive | DEPRECATED | Drive Queue path (contract §6 exclusion); lazily imported only by the deprecated Queue UI |
| 178 | `filename_normalizer.py` | filename/file handling | ACTIVE | week/lesson detection, cleanup, standard stem, first-free lesson; imported by gui_main |
| 179 | `frontend-tauri/.gitignore` | config/settings | SUPPORTING | build/dev config |
| 180 | `frontend-tauri/README.md` | config/settings | SUPPORTING | Tauri shell config/assets |
| 181 | `frontend-tauri/index.html` | config/settings | SUPPORTING | Tauri shell config/assets |
| 182 | `frontend-tauri/package-lock.json` | config/settings | SUPPORTING | Tauri shell config/assets |
| 183 | `frontend-tauri/package.json` | config/settings | SUPPORTING | Tauri shell config/assets |
| 184 | `frontend-tauri/public/tauri.svg` | config/settings | SUPPORTING | Tauri shell config/assets |
| 185 | `frontend-tauri/public/vite.svg` | config/settings | SUPPORTING | Tauri shell config/assets |
| 186 | `frontend-tauri/src-tauri/.gitignore` | config/settings | SUPPORTING | build/dev config |
| 187 | `frontend-tauri/src-tauri/Cargo.lock` | config/settings | SUPPORTING | Tauri shell config/assets |
| 188 | `frontend-tauri/src-tauri/Cargo.toml` | config/settings | SUPPORTING | Tauri shell config/assets |
| 189 | `frontend-tauri/src-tauri/build.rs` | config/settings | SUPPORTING | Tauri shell config/assets |
| 190 | `frontend-tauri/src-tauri/capabilities/default.json` | config/settings | SUPPORTING | Tauri shell config/assets |
| 191 | `frontend-tauri/src-tauri/icons/128x128.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 192 | `frontend-tauri/src-tauri/icons/128x128@2x.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 193 | `frontend-tauri/src-tauri/icons/32x32.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 194 | `frontend-tauri/src-tauri/icons/Square107x107Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 195 | `frontend-tauri/src-tauri/icons/Square142x142Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 196 | `frontend-tauri/src-tauri/icons/Square150x150Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 197 | `frontend-tauri/src-tauri/icons/Square284x284Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 198 | `frontend-tauri/src-tauri/icons/Square30x30Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 199 | `frontend-tauri/src-tauri/icons/Square310x310Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 200 | `frontend-tauri/src-tauri/icons/Square44x44Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 201 | `frontend-tauri/src-tauri/icons/Square71x71Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 202 | `frontend-tauri/src-tauri/icons/Square89x89Logo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 203 | `frontend-tauri/src-tauri/icons/StoreLogo.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 204 | `frontend-tauri/src-tauri/icons/icon.icns` | config/settings | SUPPORTING | Tauri shell config/assets |
| 205 | `frontend-tauri/src-tauri/icons/icon.ico` | config/settings | SUPPORTING | Tauri shell config/assets |
| 206 | `frontend-tauri/src-tauri/icons/icon.png` | config/settings | SUPPORTING | Tauri shell config/assets |
| 207 | `frontend-tauri/src-tauri/src/backend_launcher.rs` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 208 | `frontend-tauri/src-tauri/src/lib.rs` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 209 | `frontend-tauri/src-tauri/src/main.rs` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 210 | `frontend-tauri/src-tauri/tauri.conf.json` | config/settings | SUPPORTING | Tauri shell config/assets |
| 211 | `frontend-tauri/src/App.css` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 212 | `frontend-tauri/src/App.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 213 | `frontend-tauri/src/assets/react.svg` | config/settings | SUPPORTING | Tauri shell config/assets |
| 214 | `frontend-tauri/src/components/BackendConnectionStatus.tsx` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 215 | `frontend-tauri/src/components/Dashboard.tsx` | UI/runtime | ACTIVE | Tauri Dashboard placeholder (superseded by §5A) |
| 216 | `frontend-tauri/src/components/DriveUploadStatus.tsx` | Google Drive | ACTIVE | Drive status UI (Phase 23D) |
| 217 | `frontend-tauri/src/components/EngineSelector.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 218 | `frontend-tauri/src/components/FolderPickerPanel.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 219 | `frontend-tauri/src/components/JobTable.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 220 | `frontend-tauri/src/components/LogPanel.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 221 | `frontend-tauri/src/components/ProgressCards.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 222 | `frontend-tauri/src/data/mockJobs.ts` | test/probe/validation | SUPPORTING | mock data |
| 223 | `frontend-tauri/src/hooks/useBackendJobs.ts` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 224 | `frontend-tauri/src/hooks/useBackendStatus.ts` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 225 | `frontend-tauri/src/lib/backendJobClient.ts` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 226 | `frontend-tauri/src/lib/backendLauncherClient.ts` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 227 | `frontend-tauri/src/main.tsx` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 228 | `frontend-tauri/src/services/backendClient.ts` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 229 | `frontend-tauri/src/services/backendLauncherClient.ts` | UI/runtime | ACTIVE | Tauri shell: backend auto-start/health/cleanup (RT-001/002) |
| 230 | `frontend-tauri/src/types.ts` | UI/runtime | ACTIVE | Tauri React UI (Phase 18-23) |
| 231 | `frontend-tauri/src/vite-env.d.ts` | config/settings | SUPPORTING | Tauri shell config/assets |
| 232 | `frontend-tauri/tsconfig.json` | config/settings | SUPPORTING | Tauri shell config/assets |
| 233 | `frontend-tauri/tsconfig.node.json` | config/settings | SUPPORTING | Tauri shell config/assets |
| 234 | `frontend-tauri/vite.config.ts` | config/settings | SUPPORTING | Tauri shell config/assets |
| 235 | `gdrive_result_uploader.py` | Google Drive | ACTIVE | Drive OAuth, classification, 4-file update-or-create (called from gui_main) |
| 236 | `google_drive_uploader.py` | Google Drive | ACTIVE | Drive OAuth, classification, 4-file update-or-create (called from gui_main) |
| 237 | `gui_main.py` | UI/runtime | ACTIVE | PySide v0.9.0 main app: queue, Local/Colab control, Folders, Dashboard, tray/toast, shutdown, settings, live watcher |
| 238 | `requirements-build-sidecar.txt` | config/settings | SUPPORTING | build/dev config |
| 239 | `requirements-dev.txt` | config/settings | SUPPORTING | build/dev config |
| 240 | `scripts/build_tauri_backend_sidecar.ps1` | config/settings | SUPPORTING | sidecar build script |
| 241 | `scripts/manual_test_direct_colab_http_chunked.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 242 | `scripts/manual_test_direct_colab_http_single_file.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 243 | `scripts/probe_backend_direct_colab_http_adapter.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 244 | `scripts/probe_backend_direct_colab_http_chunk_merge.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 245 | `scripts/probe_backend_direct_colab_http_chunk_tail_skip.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 246 | `scripts/probe_backend_job_runner_adapter.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 247 | `scripts/probe_backend_local_job_queue.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 248 | `scripts/probe_completed_queue_rows_global_refresh.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 249 | `scripts/probe_drive_queue_eta_status_ui.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 250 | `scripts/probe_drive_queue_output_sync_finalization.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 251 | `scripts/probe_drive_queue_performance_guards.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 252 | `scripts/probe_drive_queue_progress_stability.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 253 | `scripts/probe_drive_queue_registration_retry.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 254 | `scripts/probe_drive_queue_skips_completed_rows.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 255 | `scripts/probe_drive_queue_start_does_not_block_on_filename_classification.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 256 | `scripts/probe_drive_queue_start_ui_guards.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 257 | `scripts/probe_drive_queue_submission_worker_lifecycle.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 258 | `scripts/probe_drive_queue_ui_state_stability.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 259 | `scripts/probe_drive_queue_upload_progress_timeout.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 260 | `scripts/probe_google_drive_auth.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 261 | `scripts/probe_google_drive_backend_service_fallback.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 262 | `scripts/probe_google_drive_queue_files.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 263 | `scripts/probe_google_drive_queue_gui_output_sync.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 264 | `scripts/probe_google_drive_queue_gui_polling.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 265 | `scripts/probe_google_drive_queue_gui_submission.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 266 | `scripts/probe_google_drive_queue_metadata.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 267 | `scripts/probe_google_drive_queue_oneclick_worker.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 268 | `scripts/probe_google_drive_queue_root.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 269 | `scripts/probe_google_drive_queue_worker_e2e.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 270 | `scripts/probe_google_drive_queue_worker_real_whisper.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 271 | `scripts/probe_google_drive_upload_isolation.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 272 | `scripts/probe_phase10_5_colab_http_ui_progress.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 273 | `scripts/probe_phase10_gdrive_result_upload.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 274 | `scripts/probe_phase10_gui_gdrive_upload_integration.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 275 | `scripts/probe_phase11_ui_simplification.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 276 | `scripts/probe_phase12a_colab_cli_wsl2.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 277 | `scripts/probe_phase12c_wsl_path_preflight.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 278 | `scripts/probe_phase12d_colab_oauth_safety.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 279 | `scripts/probe_phase12e_colab_oauth_only_feasibility.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 280 | `scripts/probe_phase12f_cpu_runtime_smoke_gate.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 281 | `scripts/probe_phase13b_env_supplemental_diagnosis.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 282 | `scripts/probe_phase13b_tauri_dev_env_survey.py` | test/probe/validation | EXPERIMENTAL | Colab CLI/WSL/env research probes |
| 283 | `scripts/probe_phase13c_tauri_scaffold_structure.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 284 | `scripts/probe_phase13d_react_screen_skeleton.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 285 | `scripts/probe_phase13e_backend_connection_poc.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 286 | `scripts/probe_phase14a_tauri_backend_launcher_design.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 287 | `scripts/probe_phase14b_tauri_backend_launcher_command_stub.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 288 | `scripts/probe_phase14c_fastapi_backend_launcher_start_stop_poc.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 289 | `scripts/probe_phase14d_launcher_ui_closeout.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 290 | `scripts/probe_phase15_tauri_execution_validation_closeout.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 291 | `scripts/probe_phase15a_frontend_dependency_install_build_preflight.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 292 | `scripts/probe_phase15b_rust_tauri_compile_check_validation.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 293 | `scripts/probe_phase15c1_tauri_dev_window_launch_poc.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 294 | `scripts/probe_phase15c2_backend_launcher_start_stop_poc.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 295 | `scripts/probe_phase15e1_tauri_ui_design_source_application.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 296 | `scripts/probe_phase15e2_icon_tray_notification_design_review.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 297 | `scripts/probe_phase15e_tauri_ui_design_application_closeout.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 298 | `scripts/probe_phase16_gdrive_queue_legacy_closeout.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 299 | `scripts/probe_phase16a_gdrive_queue_legacy_inventory.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 300 | `scripts/probe_phase16b_gdrive_queue_legacy_docs_cleanup.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 301 | `scripts/probe_phase16c_gdrive_queue_legacy_guard.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 302 | `scripts/probe_phase17a_tauri_actual_job_flow_gap_analysis.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 303 | `scripts/probe_phase18a_tauri_frontend_job_client.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 304 | `scripts/probe_phase18b_tauri_ui_job_flow_wiring.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 305 | `scripts/probe_phase18c2_tauri_job_flow_missing_fields_fix.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 306 | `scripts/probe_phase18c3_tauri_actual_job_flow_final_acceptance.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 307 | `scripts/probe_phase18c_tauri_actual_job_flow_wiring_acceptance.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 308 | `scripts/probe_phase19a2_tauri_backend_launcher_runtime_verification.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 309 | `scripts/probe_phase19a_tauri_runtime_validation.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 310 | `scripts/probe_phase20a_tauri_job_create_smoke_validation.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 311 | `scripts/probe_phase20b_tauri_ui_job_create_smoke.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 312 | `scripts/probe_phase20c_tauri_job_start_status_transition_smoke.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 313 | `scripts/probe_phase21a_local_whisper_backend_adapter_wiring.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 314 | `scripts/probe_phase21b_local_whisper_real_mp3_smoke.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 315 | `scripts/probe_phase21c_tauri_ui_local_whisper_real_mp3_smoke.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 316 | `scripts/probe_phase22a_clean_build_release_decision.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 317 | `scripts/probe_phase22b_msi_only_clean_packaging_recovery.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 318 | `scripts/probe_phase23a_tauri_local_whisper_output_bundle_contract.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 319 | `scripts/probe_phase23b_installed_backend_runtime.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 320 | `scripts/probe_phase23c_installed_local_whisper_output_bundle.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 321 | `scripts/probe_phase23d2_drive_bundle_upload_offline.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 322 | `scripts/probe_phase23d3b2_unicode_job_payload.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 323 | `scripts/probe_phase23d3b3_drive_frozen_imports.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 324 | `scripts/probe_phase23d3b5_drive_job_projection.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 325 | `scripts/probe_phase7a_colab_http_ui_options.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 326 | `scripts/probe_phase7b_gui_colab_http_job_runner.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 327 | `scripts/probe_phase7d_pyside_ui_layout.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 328 | `scripts/probe_progress_smooth_1_to_100.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 329 | `scripts/probe_queue_status_badge_widget.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 330 | `scripts/probe_smart_rename_protects_standard_files.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 331 | `scripts/run_phase23c_installed_tauri_ui_smoke.ps1` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 332 | `scripts/smoke_drive_queue_local_backend.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 333 | `scripts/test_drive_queue_backend_contracts.py` | test/probe/validation | DEPRECATED | Drive Queue probes |
| 334 | `scripts/test_smart_rename.py` | test/probe/validation | SUPPORTING | validation probe/test evidence |
| 335 | `transcribe_helper.ico` | UI/runtime | SUPPORTING | icons/fonts |
| 336 | `transcribe_helper.svg` | UI/runtime | SUPPORTING | icons/fonts |
| 337 | `전사도우미.spec` | config/settings | SUPPORTING | PyInstaller build of the PySide app |
