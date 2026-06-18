# Silence — Open-source Real-time AI Noise Suppression

<div align="center">

![Silence Logo](assets/icon.png)

**Silence** 是一款完全開源的 Windows 實時 AI 降噪軟體。  
透過 DeepFilterNet 3 模型與 DirectML GPU 加速，以極低延遲消除鍵盤聲、風扇聲、底噪等各種環境噪音。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue.svg)](https://www.microsoft.com/windows)

</div>

---

## ✨ 功能

- 🎤 **AI 實時降噪** — 基於 DeepFilterNet 3，業界頂尖開源降噪模型
- ⚡ **極低延遲** — DirectML GPU 加速，~15–25ms 端對端延遲
- 🎛️ **100 級強度調節** — 精細控制降噪攻擊性與語音保真度
- 📊 **VU Meter** — 即時麥克風電平顯示（綠/黃/紅 + dBFS）
- 🔌 **虛擬麥克風** — 透過 VB-Cable 供 Discord、Zoom、OBS 使用
- 🖥️ **系統托盤常駐** — 輕量後台執行，一鍵開關
- 🌐 **完全開源** — 程式碼 + 模型權重全部 Apache 2.0 公開

## 🎯 消除噪音類型

| 噪音類型 | 效果 |
|---------|------|
| 鍵盤打字聲 / 滑鼠點擊聲 | ✅ 優秀 |
| 風扇 / 冷氣機運轉聲 | ✅ 優秀 |
| 底噪（嗡嗡聲、電流聲）| ✅ 優秀 |
| 環境聲（馬路聲、人聲）| ✅ 良好 |
| 多語言語音保護（中文/英文）| ✅ 支援 |

## 🚀 快速開始

### 系統需求

- Windows 10 1903+ 或 Windows 11
- 任意 GPU（NVIDIA / AMD / Intel 核顯，透過 DirectML 加速）
- 已安裝 [VB-Cable](https://vb-audio.com/Cable/)（免費虛擬音訊驅動器）

### 安裝

1. 從 [Releases](https://github.com/yourusername/silence/releases) 下載最新 `Silence-Setup.exe`
2. 執行安裝程式
3. 如尚未安裝 VB-Cable，Silence 將引導你完成安裝
4. 在通話軟體（Discord/Zoom）中選擇 `CABLE Output (VB-Audio)` 作為麥克風

### 從原始碼執行

```bash
# 需要 uv (https://docs.astral.sh/uv/)
git clone https://github.com/yourusername/silence.git
cd silence

# 建立虛擬環境並安裝依賴
uv sync

# 執行
uv run python -m silence
```

## 🛠️ 開發環境

```bash
# 安裝所有依賴（含開發工具）
uv sync --all-extras

# 執行
uv run python -m silence

# 打包為 exe
uv run pyinstaller silence.spec
```

## 📐 架構

```
麥克風輸入 (48kHz)
    │
    ├──▶ VU Meter 電平計算
    │
    ▼
DeepFilterNet 3 (ONNX + DirectML)
    │
    ▼
VB-Cable 虛擬麥克風輸出
    │
    ▼
Discord / Zoom / OBS
```

## 📄 授權

本專案使用 [Apache 2.0](LICENSE) 授權開源。  
DeepFilterNet 模型同樣為 Apache 2.0 授權。

## 🙏 致謝

- [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) — 核心降噪模型
- [VB-Cable](https://vb-audio.com/Cable/) — 虛擬音訊驅動器
- [ONNX Runtime](https://onnxruntime.ai/) — 跨平台推理引擎
