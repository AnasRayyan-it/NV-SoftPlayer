# NV-SoftPlayer out-of-process Windows Media Player host.
# Runs in powershell.exe so volume does not affect NVDA speech.
Add-Type -AssemblyName System.Windows.Forms
$ErrorActionPreference = 'Continue'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$src = @"
using System;
using System.Threading;
using System.Collections.Concurrent;

public static class PipeReader {
    private static ConcurrentQueue<string> q = new ConcurrentQueue<string>();
    public static void Start() {
        Thread t = new Thread(() => {
            string line;
            while ((line = Console.ReadLine()) != null) {
                line = line.Trim();
                if (line.Length > 0) q.Enqueue(line);
            }
            q.Enqueue("{\"cmd\":\"quit\"}");
        });
        t.IsBackground = true;
        t.Start();
    }
    public static string TryRead() {
        string res;
        if (q.TryDequeue(out res)) return res;
        return null;
    }
}
$dllCandidates = @(
	(Join-Path $PSScriptRoot "bin\PipeReader.dll"),
	(Join-Path $PSScriptRoot "PipeReader.dll")
)
$loaded = $false
foreach ($dll in $dllCandidates) {
	if (Test-Path $dll) {
		try {
			Add-Type -Path $dll
			[PipeReader]::Start()
			$loaded = $true
			break
		} catch {}
	}
}
if (-not $loaded) {
	try {
		Add-Type -TypeDefinition $src
		[PipeReader]::Start()
	} catch {}
}

$wmp = New-Object -ComObject WMPlayer.OCX
try { $wmp.settings.autoStart = $false } catch {}
try { $wmp.settings.enableErrorDialogs = $false } catch {}
try { $wmp.uiMode = 'invisible' } catch {}

function Write-Msg([string]$s) {
	[Console]::Out.WriteLine($s)
	[Console]::Out.Flush()
}

Write-Msg '{"ok":true,"event":"ready"}'

$running = $true
while ($running) {
	[System.Windows.Forms.Application]::DoEvents()
	$raw = $null
	try {
		$raw = [PipeReader]::TryRead()
	} catch {
		$raw = $null
	}
	if ($null -ne $raw) {
		try {
			$j = $raw | ConvertFrom-Json
			$cmd = [string]$j.cmd
			switch ($cmd) {
				'load' {
					$wmp.URL = [string]$j.url
					try { $wmp.controls.stop() } catch {}
					try { $wmp.controls.currentPosition = 0 } catch {}
					Write-Msg '{"ok":true}'
				}
				'play' {
					$wmp.controls.play()
					Write-Msg '{"ok":true}'
				}
				'pause' {
					$wmp.controls.pause()
					Write-Msg '{"ok":true}'
				}
				'stop' {
					$wmp.controls.stop()
					try { $wmp.controls.currentPosition = 0 } catch {}
					Write-Msg '{"ok":true}'
				}
				'seek' {
					$wmp.controls.currentPosition = [double]$j.value
					Write-Msg '{"ok":true}'
				}
				'volume' {
					$wmp.settings.volume = [int]$j.value
				}
				'query' {
					$st = 1
					$pos = 0.0
					$dur = 0.0
					$vol = 100
					try { $st = [int]$wmp.playState } catch {}
					try { $pos = [double]$wmp.controls.currentPosition } catch {}
					try { $dur = [double]$wmp.currentMedia.duration } catch {}
					try { $vol = [int]$wmp.settings.volume } catch {}
					if ($dur -lt 0) { $dur = 0 }
					if ($pos -lt 0) { $pos = 0 }
					Write-Msg ("{`"ok`":true,`"state`":$st,`"pos`":$pos,`"dur`":$dur,`"vol`":$vol}")
				}
				'quit' {
					try { $wmp.controls.stop() } catch {}
					try { $wmp.close() } catch {}
					Write-Msg '{"ok":true}'
					$running = $false
				}
				default {
					Write-Msg '{"ok":false,"error":"unknown"}'
				}
			}
		} catch {
			Write-Msg '{"ok":false,"error":"exception"}'
		}
	} else {
		Start-Sleep -Milliseconds 10
	}
}
try { $wmp.close() } catch {}