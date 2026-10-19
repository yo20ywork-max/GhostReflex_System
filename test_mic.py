import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav

fs = 16000
duration = 4  # 錄製 4 秒

print("\n🎤 請看著倒數，對麥克風清楚講一次「開啟 YouTube」...")
audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
sd.wait()

wav.write("mic_test.wav", fs, audio)
rms = np.sqrt(np.mean((audio.astype(float)/32768.0)**2))

print(f"✅ 錄音結束！音量強度 RMS: {rms:.4f}")
print("請到專案資料夾點開「mic_test.wav」播放聽聽看！")