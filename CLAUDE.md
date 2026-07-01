# IoT project

You are working on a IoT & AI Project that aims to track 3 parameters with Parkinson patients, using a custom built Raspberry Pi Zero setup with 3 sensors:
- Microphone for voice recording  (output: .wav file)
- Accelerometer / Gyroscope attached to the leg (.csv)
- Camera with face recording (.h264)

The experiment is as follows: the patient puts on the setup with all sensors, and is asked to walk around 10m while doing some movements with hands and saying the BA sound. The goal of the project is to test the hypothesis that the wide body movements help improve the patient stability and voice.

Microphone is located near the face to track: mean loudness, vocal activity ratio, loudness variability, loudness trend.
Accelerometer is attached to the leg (close to foot) to track step count, cadence, gait regularity, and activity ratio.
Gyroscope is needed for mean rotation and rotation variability.
Video: mean mouth opening, mouth opening rate, opening variability, opening trend.

Tech Stack:
- Python with uv (package manager and runner)
- librosa
- opencv & mediapipe
- Pandas
- Numpy
- Matplotlib

