from splitter.unit_economics import build_unit_economics


def test_unit_economics_reports_scoped_gpu_and_storage_estimates() -> None:
    stem_reference = {
        "provider": "s3",
        "bucket": "audio",
        "key": "jobs/job-1/vocals.wav",
        "size_bytes": 1_000,
    }
    payload = {
        "input_object": {
            "provider": "s3",
            "bucket": "audio",
            "key": "inputs/song.wav",
            "size_bytes": 500,
        },
        "object_artifacts": {
            "broad_stems": {
                "vocals": stem_reference,
                "duplicate_manifest_entry": stem_reference,
            }
        },
        "object_bundle": {
            "provider": "s3",
            "bucket": "audio",
            "key": "jobs/job-1/stems.zip",
            "size_bytes": 2_000,
        },
        "timings": {
            "gpu_type": "T4",
            "worker_total_seconds": 120,
            "input_duration_seconds": 60,
            "model_runs": [
                {"total_seconds": 50},
                {"total_seconds": 55},
            ],
        },
    }

    economics = build_unit_economics(payload)

    assert economics["evidence_level"] == "public_rate_estimate_not_invoice"
    assert economics["estimated_base_gpu_cost_usd"] == 0.01968
    assert economics["estimated_base_gpu_cost_per_audio_minute_usd"] == 0.01968
    assert economics["worker_realtime_factor"] == 2.0
    assert economics["model_seconds"] == 105.0
    assert economics["storage"] == {
        "input_bytes": 500,
        "input_object_count": 1,
        "output_stem_bytes": 1_000,
        "output_stem_object_count": 1,
        "bundle_bytes": 2_000,
        "bundle_object_count": 1,
        "total_unique_bytes": 3_500,
    }


def test_unit_economics_sums_heterogeneous_gpu_allocations() -> None:
    economics = build_unit_economics(
        {
            "timings": {
                "gpu_type": "heterogeneous",
                "worker_total_seconds": 58,
                "input_duration_seconds": 60,
                "gpu_allocations": [
                    {
                        "role": "broad",
                        "model_key": "bs_roformer_sw",
                        "gpu_type": "L4",
                        "gpu_seconds": 52,
                    },
                    {
                        "role": "drums",
                        "model_key": "mdx23c_drumsep_jarredou_aufr33",  # gitleaks:allow
                        "gpu_type": "T4",
                        "gpu_seconds": 28,
                    },
                ],
            }
        }
    )

    assert economics["gpu_type"] == "HETEROGENEOUS"
    assert economics["gpu_seconds"] == 80.0
    assert economics["worker_wall_seconds"] == 58.0
    assert economics["worker_realtime_factor"] == 0.9667
    assert economics["aggregate_gpu_realtime_factor"] == 1.3333
    assert economics["estimated_base_gpu_cost_usd"] == 0.016136
    assert [allocation["gpu_type"] for allocation in economics["gpu_allocations"]] == ["L4", "T4"]
