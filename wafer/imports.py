from __future__ import annotations
import torch, torcheval
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader

from datasets import load_dataset, Dataset

import numpy as np
import pandas as pd
from PIL import Image
from matplotlib import animation
import matplotlib.pyplot as plt

import time
from tqdm.notebook import tqdm
from IPython.display import display, clear_output, HTML

def noop (x=None, *args, **kwargs):
    "Do nothing"
    return x