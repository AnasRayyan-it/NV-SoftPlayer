# -*- coding: UTF-8 -*-
"""
Build script to package the NV-SoftPlayer NVDA add-on into a .nvda-addon installer.
Includes globalPlugins, manifest.ini, readme.txt, and bundled binaries (ffmpeg.exe, yt-dlp.exe).
"""

import os
import sys
import zipfile
import re


def parse_manifest(manifest_path):
	data = {}
	if not os.path.isfile(manifest_path):
		return data
	with open(manifest_path, "r", encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			if "=" in line:
				key, val = line.split("=", 1)
				key = key.strip()
				val = val.strip().strip('"').strip("'")
				data[key] = val
	return data


def build():
	root_dir = os.path.abspath(os.path.dirname(__file__))
	manifest_path = os.path.join(root_dir, "manifest.ini")
	
	if not os.path.isfile(manifest_path):
		print("[ERROR] manifest.ini not found in:", root_dir)
		sys.exit(1)

	manifest = parse_manifest(manifest_path)
	addon_name = manifest.get("name", "NV-SoftPlayer")
	addon_version = manifest.get("version", "1.0.0")

	output_filename = f"{addon_name}-{addon_version}.nvda-addon"
	output_path = os.path.join(root_dir, output_filename)

	# Verify required binaries
	bin_dir = os.path.join(root_dir, "globalPlugins", "NV-SoftPlayer", "bin")
	ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
	ytdlp_path = os.path.join(bin_dir, "yt-dlp.exe")

	print("=" * 60)
	print(f"Building NVDA Add-on: {addon_name} v{addon_version}")
	print("=" * 60)

	if os.path.isfile(ffmpeg_path):
		print(f"[OK] Bundling ffmpeg.exe ({os.path.getsize(ffmpeg_path) / (1024*1024):.1f} MB)")
	else:
		print("[WARNING] ffmpeg.exe NOT found in bin folder!")

	if os.path.isfile(ytdlp_path):
		print(f"[OK] Bundling yt-dlp.exe ({os.path.getsize(ytdlp_path) / (1024*1024):.1f} MB)")
	else:
		print("[WARNING] yt-dlp.exe NOT found in bin folder!")

	ignored_dirs = {"__pycache__", ".git", ".vscode", ".idea", "dist", "build"}
	ignored_exts = {".pyc", ".pyo", ".nvda-addon", ".zip", ".delete"}
	ignored_files = {"build_addon.py", "build_addon.ps1"}

	print("\nCompressing files into installer package...")
	count = 0
	with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
		for dirpath, dirnames, filenames in os.walk(root_dir):
			# Filter directories in-place
			dirnames[:] = [d for d in dirnames if d not in ignored_dirs]

			for filename in filenames:
				if filename in ignored_files:
					continue
				_, ext = os.path.splitext(filename)
				if ext.lower() in ignored_exts:
					continue

				abs_file = os.path.join(dirpath, filename)
				if abs_file == output_path:
					continue

				rel_path = os.path.relpath(abs_file, root_dir).replace("\\", "/")
				zf.write(abs_file, rel_path)
				count += 1
				print(f"  + {rel_path}")

	size_mb = os.path.getsize(output_path) / (1024 * 1024)
	print("-" * 60)
	print(f"[SUCCESS] Package created successfully!")
	print(f"File: {output_path}")
	print(f"Files included: {count}")
	print(f"Total package size: {size_mb:.2f} MB")
	print("=" * 60)


if __name__ == "__main__":
	build()
