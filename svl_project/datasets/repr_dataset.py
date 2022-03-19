import itertools
from argparse import ArgumentParser
from numpy.lib.utils import deprecate
import pandas as pd
from torch.utils.data import Dataset, IterableDataset
import os
import soundfile as sf
import torch
from PIL import Image
import torchvision.transforms as T

import json
import cv2
import time
import matplotlib.pyplot as plt

from torch.utils.data.dataloader import DataLoader
import torchaudio
import math
from re import L
from collections import deque
from torch.nn.utils.rnn import pad_sequence
from svl_project.datasets.base import BaseDataset
import numpy as np
import torch.nn.functional as F

EPS = 1e-8

class VisionGripperDataset(BaseDataset):
    def __getitem__(self, idx):
        trial, timestamps, _, num_frames = self.get_episode(idx, load_audio=False)
        timestep = torch.randint(high=num_frames, size=()).item()
        return self.resize_image(self.load_image(trial, "cam_gripper_color", timestep), (64, 64))

class VisionFixedDataset(BaseDataset):
    def __getitem__(self, idx):
        trial, timestamps, _, num_frames = self.get_episode(idx, load_audio=False)
        timestep = torch.randint(high=num_frames, size=()).item()
        return self.resize_image(self.load_image(trial, "cam_fixed_color", timestep), (64, 64))

class GelsightFrameDataset(BaseDataset):
    def __getitem__(self, idx):
        trial, timestamps, _, num_frames = self.get_episode(idx, load_audio=False)
        timestep = torch.randint(high=num_frames, size=()).item()
        original_img = self.load_image(trial, "left_gelsight_frame", timestep)
        img =  self.resize_image(original_img - self.gelsight_offset, (64, 64)) + 0.5
        img = img.clamp(0, 1)
        # img = img.mean(0, keepdim=True).expand(3, 64, 64)
        return img

@DeprecationWarning
class TripletDataset(Dataset):
    def __init__(self, log_file, sil_ratio=0.2, data_folder="data/test_recordings_0123"):
        """
        neg_ratio: ratio of silence audio clips to sample
        """
        super().__init__()
        self.logs = pd.read_csv(log_file)
        self.data_folder = data_folder
        sr = 16000
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=sr, n_fft=int(sr * 0.025), hop_length=int(sr * 0.01), n_mels=64
        )
        self.sil_ratio = sil_ratio

    def __getitem__(self, idx):
        format_time = self.logs.iloc[idx].Time.replace(":", "_")
        trial = os.path.join(self.data_folder, format_time)
        audio1, sr = sf.read(os.path.join(trial, "audio_holebase.wav"))
        audio2, sr = sf.read(os.path.join(trial, "audio_gripper.wav"))
        assert sr == 16000
        resolution = sr // 10  # number of audio samples in each video frame
        # print(audio1.max(), audio1.min(), audio2.max(), audio2.min(), audio1.shape, audio2.shape)
        assert audio1.shape == audio2.shape
        audio = torch.as_tensor(np.stack([audio1, audio2], 0)).float()

        # read camera frames
        cam_video = cv2.VideoCapture(os.path.join(trial, "cam_gripper.avi"))
        success, cam_frame = cam_video.read()
        cam_frames = []
        while success:
            cam_frames.append(cam_frame)
            success, cam_frame = cam_video.read()
        cam_frames = torch.as_tensor(np.stack(cam_frames, 0))
        # read gelsight frames
        gs_video = cv2.VideoCapture(os.path.join(trial, "gs.avi"))
        success, gs_frame = gs_video.read()
        gs_frames = []
        while success:
            gs_frames.append(gs_frame)
            success, gs_frame = gs_video.read()
        gs_frames = torch.as_tensor(np.stack(gs_frames, 0))
        # see how many frames there are
        assert cam_frames.size(0) == gs_frames.size(0)
        num_frames = cam_frames.size(0)

        # voice activity detection
        audio_frames = audio.unfold(dimension=-1, size=resolution, step=resolution)
        energy = torch.pow(audio_frames, 2).sum(-1).sum(0) # user the gripper piezo
        # plt.plot(energy)
        # plt.plot(torch.ones(energy.shape) * 2)
        # print(trial)
        # plt.show()
        # sample anchor times
        if torch.rand(()) > self.sil_ratio and (energy > 2.5).any():  # sample anchor with audio event
            anchor_choices = torch.nonzero(energy > 2.5)
            anchor = anchor_choices[
                torch.randint(high=anchor_choices.size(0), size=())
            ].item()
        else:
            anchor_choices = torch.nonzero(energy < 2.5)
            anchor = anchor_choices[
                torch.randint(high=anchor_choices.size(0), size=())
            ].item()
        # get image and gelsight
        cam_pos = cam_frames[anchor]
        gs_pos = gs_frames[anchor]
        # audio length is 1 second
        audio_start = anchor * resolution - sr // 2
        audio_end = audio_start + sr
        audio_pos = clip_audio(audio, audio_start, audio_end)

        assert audio_pos.size(1) == sr
        spec = self.mel(audio_pos)
        log_spec = torch.log(spec + EPS)

        # sample negative index
        upper_bound = anchor - 5
        lower_bound = anchor + 5
        negative_range = torch.Tensor([]).int()
        if upper_bound > 0:
            negative_range = torch.cat([negative_range, torch.arange(0, upper_bound)])
        if lower_bound < num_frames:
            negative_range = torch.cat(
                [negative_range, torch.arange(lower_bound, num_frames)]
            )
        negative = negative_range[torch.randint(high=negative_range.size(0), size=())]
        cam_neg = cam_frames[negative]

        return (
            cam_pos.permute(2, 0, 1) / 255,
            gs_pos.permute(2, 0, 1) / 255,
            log_spec,
            cam_neg.permute(2, 0, 1) / 255,
        )

    def __len__(self):
        return len(self.logs)

@DeprecationWarning
class FuturePredDataset(Dataset):
    def __init__(self, log_file, max_len, data_folder="data"):
        """
        neg_ratio: ratio of silence audio clips to sample
        """
        super().__init__()
        self.logs = pd.read_csv(log_file)
        self.data_folder = data_folder
        sr = 16000
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=sr, n_fft=int(sr * 0.025), hop_length=int(sr * 0.01), n_mels=64
        )
        self.max_len = max_len

    def __getitem__(self, idx):
        trial = os.path.join(self.data_folder, self.logs.iloc[idx].Time)
        audio1, sr = sf.read(os.path.join(trial, "audio_holebase.wav"))
        audio2, sr = sf.read(os.path.join(trial, "audio_gripper.wav"))
        assert sr == 16000
        resolution = sr // 10  # number of audio samples in each video frame
        # print(audio1.max(), audio1.min(), audio2.max(), audio2.min(), audio1.shape, audio2.shape)
        assert audio1.shape == audio2.shape
        audio = torch.as_tensor(np.stack([audio1, audio2], 0)).float()

        # read camera frames
        cam_video = cv2.VideoCapture(os.path.join(trial, "cam_gripper.avi"))
        success, cam_frame = cam_video.read()
        cam_frames = []
        while success:
            cam_frames.append(cam_frame)
            success, cam_frame = cam_video.read()
        cam_frames = torch.as_tensor(np.stack(cam_frames, 0)).permute(0, 3, 1, 2) / 255

        # print("cam_frames shape: {}".format(cam_frames.shape))

        # read gelsight frames
        gs_video = cv2.VideoCapture(os.path.join(trial, "gs.avi"))
        success, gs_frame = gs_video.read()
        gs_frames = []
        while success:
            gs_frames.append(gs_frame)
            success, gs_frame = gs_video.read()
        gs_frames = torch.as_tensor(np.stack(gs_frames, 0)).permute(0, 3, 1, 2) / 255

        # print("gs_frames shape: {}".format(gs_frames.shape))
        # see how many frames there are
        assert cam_frames.size(0) == gs_frames.size(0)
        num_frames = cam_frames.size(0)

        # clip number of frames used for training
        if num_frames > self.max_len and self.max_len > 0:
            start = torch.randint(high=num_frames - self.max_len + 1, size=())
            end = start + self.max_len
        else:
            start = 0
            end = num_frames

        cam_frames = cam_frames[start:end]
        gs_frames = gs_frames[start:end]

        with open(os.path.join(trial, "timestamps.json")) as ts:
            timestamps = json.load(ts)

        log_specs = []
        actions = []

        for timestep in range(start, end):
            # get log audio spectrum
            audio_start = timestep * resolution - sr // 2
            audio_end = audio_start + sr
            audio_clip = clip_audio(audio, audio_start, audio_end)
            assert audio_clip.size(1) == sr
            spec = self.mel(audio_clip)
            log_spec = torch.log(spec + EPS)
            # get action
            action_c = timestamps["action_history"][timestep]
            xy_space = {-0.006: 0, 0: 1, 0.006: 2}
            z_space = {-0.003: 0, 0: 1, 0.003: 2}
            x = xy_space[action_c[0]]
            y = xy_space[action_c[1]]
            z = z_space[action_c[2]]
            action = torch.as_tensor([x, y, z])

            log_specs.append(log_spec)
            actions.append(action)
        log_specs = torch.stack(log_specs, dim=0)
        actions = torch.stack(actions, dim=0)

        return cam_frames, log_specs, gs_frames, actions

    def __len__(self):
        return len(self.logs)



if __name__ == "__main__":
    log_file = "data/episode_times_0214.csv"
    data_folder = "data/test_recordings_0214"
    dataset = VisionGripperDataset(log_file, data_folder)
    start = time.time()
    for data in dataset:
        print(time.time() - start)
        start = time.time()
