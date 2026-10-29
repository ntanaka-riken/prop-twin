# analysis/readme/ — トップの README の図と動画を作るスクリプト

| ファイル | 作るもの |
|---|---|
| `fig_audio_fft.py <IMG_5741.mov> ../../media/readme/audio_fft.png` | 音声 FFT の倍音コムから回転数を読む図 |
| `fig_adc_K.py ../../media/readme/adc_K.png` | ADC の逆起電力と整流子リップルから K を測る図 |
| `fig_results.py ../../media/readme/results.png` | 部分 duty・推力・閉ループの実測とツインの比較(現行 `twin/params.json`) |
| `frames.swift <in.mov> <outdir> <t0> <t1> <fps> <max_px>` | 動画からフレームを JPEG で書き出す(AVFoundation、ffmpeg 不要) |
| `compose.py out.webp <fps> <height> <dirA> [dirB]` | フレーム列(左右 2 本も可)を animated WebP にする(`img2webp`) |
| `render/obj.html` + `render/turn.mjs` | Object Capture の OBJ をヘッドレス Chrome で回して撮る(`?m=prop&elev=32&d=0.6&cx=..`) |
| `render/turn_twin.mjs`、`render/rec_twin3d.mjs` | `twin/twin3d.html` を周回 / 実時間で撮る(`python3 -m http.server 8766 --directory twin` の上で) |

`model.svg`(ツインの構成図)は手書きの SVG です。動画はリリース `media-2026-10-29` にあります。
