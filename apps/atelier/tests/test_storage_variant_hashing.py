from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from PIL import Image

from apps.atelier.staticbuild.storage import (
    VariantManifestStaticFilesStorage,
    _cfg,
)


class VariantStorageHashingTests(SimpleTestCase):
    @override_settings(
        ATELIER_IMAGE_VARIANTS={
            "enabled": ["webp", "png"],
            "max_width": 0,
            "quality": {"webp": 80, "png": 9},
            "process_ext": [".png"],
        }
    )
    def test_variants_are_written_with_final_hashed_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = VariantManifestStaticFilesStorage(location=tmpdir, base_url="/static/")

            original_rel = "images/shape/sample.png"
            hashed_rel = "images/shape/sample.abcdef123456.png"
            stem = Path(hashed_rel).stem  # 'sample.abcdef123456'
            variants_dir_rel = str(Path(hashed_rel).parent / stem)

            # Create hashed source file on disk
            img = Image.new("RGB", (32, 32), color="red")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            src_path = Path(storage.path(hashed_rel))
            src_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.write_bytes(buf.getvalue())

            cfg = _cfg()
            storage._variants_map.clear()

            storage._maybe_build_variants(original_rel, hashed_rel, cfg)

            self.assertIn(original_rel, storage._variants_map)
            mapping = storage._variants_map[original_rel]
            self.assertTrue(mapping)
            self.assertEqual(set(mapping), set(cfg.enabled))

            normalized_dir = Path(variants_dir_rel)

            for fmt, rel in mapping.items():
                self.assertIn(fmt, cfg.enabled)
                # ensure stored path is normalized and hashed
                self.assertFalse(rel.startswith("/"))
                self.assertTrue(rel.startswith(str(normalized_dir)))
                variant_path = Path(storage.path(rel))
                self.assertTrue(variant_path.exists())
                # plain (non rehashed) file should not remain
                plain_rel = str(Path(variants_dir_rel) / f"{stem}.{fmt}")
                self.assertFalse(Path(storage.path(plain_rel)).exists())
                # hashed filename pattern: stem.hash.ext
                pattern = rf"{re.escape(stem)}\.[0-9a-f]{{12,}}\.{fmt}$"
                self.assertRegex(Path(rel).name, pattern)

            # Detection helper should rediscover hashed files even without manifest cache
            saved_mapping = mapping.copy()
            storage._variants_map.clear()
            detected = storage._detect_existing_variants(original_rel, variants_dir_rel, stem, cfg)
            self.assertEqual(detected, saved_mapping)

            # _needs_regen should signal up-to-date state
            stamp_rel = str(Path(variants_dir_rel) / ".stamp")
            stamp_fs = Path(storage.path(stamp_rel))
            self.assertTrue(stamp_fs.exists())
            current_stamp = storage._build_stamp(Path(storage.path(hashed_rel)), cfg)
            self.assertFalse(storage._needs_regen(
                original_rel,
                stamp_fs,
                current_stamp,
                cfg,
                Path(storage.path(variants_dir_rel)),
                variants_dir_rel,
                stem,
            ))
