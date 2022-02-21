# from typing_extensions import Required
import sys
if '/opt/ros/kinetic/lib/python2.7/dist-packages' in sys.path:
    sys.path.remove('/opt/ros/kinetic/lib/python2.7/dist-packages')
import torch
import numpy as np
from imi_dataset import ImitationDataSet_hdf5
from imi_models import make_vision_encoder, Imitation_Baseline_Actor_Tuning
from imi_engine import ImiBaselineLearn_Tuning
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt
import os
import yaml
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint





def baselineValidate(args):
    def strip_sd(state_dict, prefix):
        """
        strip prefix from state dictionary
        """
        return {k.lstrip(prefix): v for k, v in state_dict.items() if k.startswith(prefix)}

    # get pretrained model
    val_set = ImitationDataSet_hdf5(args.val_csv, args.num_stack, args.frameskip, 432, 576, "data/test_recordings_0208_repeat")
    val_loader = DataLoader(val_set, 1, num_workers=0)
    ckpt_path = "last.ckpt"
    v_encoder = make_vision_encoder(args.embed_dim)

    actor = Imitation_Baseline_Actor_Tuning(
        v_encoder,  args)
    # actor = Immitation_Pose_Baseline_Actor(
    #     v_gripper_encoder, v_fixed_encoder, args.embed_dim, args.action_dim)
    state_dict = strip_sd(torch.load(ckpt_path)['state_dict'], 'actor.')
    print("Model's state_dict:")
    for param_tensor in state_dict:
        print(param_tensor, "\t", state_dict[param_tensor].size())
    actor.load_state_dict(state_dict)
    actor.eval()
    cnt = 0
    cor = np.array([0, 0, 0])
    wrong = np.array([0, 0, 0])

    predict = []
    real = []

    for batch in val_loader:
        v_gripper_inp, v_fixed_inp, keyboard = batch
        v_inp = v_gripper_inp + v_fixed_inp
        action_pred = actor(v_inp, True).detach().numpy()
        action_pred = action_pred.reshape(3, -1)
        action_pred = (np.argmax(action_pred, axis=1))
        keyboard = keyboard.numpy()
        for i in range(3):
            if(action_pred[i] == keyboard[0][i]):
                cor[i] += 1
            else:
                wrong[i] += 1
        predict.append(action_pred)
        real.append(keyboard)

        cnt += 1
        if cnt == 100:
            break

    predict = np.asarray(predict)
    real = np.asarray(real).reshape(cnt,3)
    fig = plt.figure(0)
    plt.title("x")
    plt.scatter(range(cnt),predict[:,0], s = 0.3)
    plt.scatter(range(cnt),real[:, 0], s = 0.3, alpha= 0.5)
    plt.xlabel("count of batches")
    plt.ylabel("actions(0:move -;1:stay;2:move +")
    plt.legend(["pred","real"])
    fig = plt.figure(1)
    plt.title("y")
    plt.scatter(range(cnt), predict[:, 1], s = 0.3)
    plt.scatter(range(cnt), real[:, 1],s = 0.3,alpha= 0.5)
    plt.xlabel("count of batches")
    plt.ylabel("actions(0:move -;1:stay;2:move +")
    plt.legend(["pred", "real"])
    fig = plt.figure(2)
    plt.title("z")
    plt.scatter(range(cnt), predict[:, 2],s = 0.3)
    plt.scatter(range(cnt), real[:, 2],s = 0.3,alpha=0.5)
    plt.xlabel("count of batches")
    plt.ylabel("actions(0:move -;1:stay;2:move +")
    plt.legend(["pred", "real"])
    plt.show()
    acc = cor / (cor + wrong)
    print(acc)

def baselineRegValidate(args):
    def strip_sd(state_dict, prefix):
        """
        strip prefix from state dictionary
        """
        return {k.lstrip(prefix): v for k, v in state_dict.items() if k.startswith(prefix)}

    # get pretrained model
    val_set = ImitationDataSet_hdf5(args.val_csv, args.num_stack, args.frameskip, 432, 576, "../test_recordings_0214")
    val_loader = DataLoader(val_set, 1, num_workers=0)
    ckpt_path = args.pretrained
    v_encoder = make_vision_encoder(args.embed_dim)

    actor = Imitation_Baseline_Actor_Tuning(
        v_encoder, args)
    state_dict = strip_sd(torch.load(ckpt_path)['state_dict'], 'actor.')
    print("Model's state_dict:")
    for param_tensor in state_dict:
        print(param_tensor, "\t", state_dict[param_tensor].size())
    actor.load_state_dict(state_dict)
    actor.eval()
    cnt = 0
    cor = np.array([0, 0, 0])
    wrong = np.array([0, 0, 0])

    predict = []
    real = []

    for batch in val_loader:
        v_gripper_inp, v_fixed_inp, keyboard = batch
        v_inp = v_gripper_inp + v_fixed_inp
        action_pred = actor(v_inp, True).detach().numpy()
        action_pred = action_pred.reshape(3)
        # action_pred = (np.argmax(action_pred, axis=1))
        keyboard = (keyboard.numpy() - 1)
        # keyboard[0][:2] = keyboard[0][:2] * 0.006
        # keyboard[0][2] = keyboard[0][2] * 0.003
        # for i in range(3):
        #     if(action_pred[i] == keyboard[0][i]):
        #         cor[i] += 1
        #     else:
        #         wrong[i] += 1
        predict.append(action_pred)
        real.append(keyboard)
        cnt += 1
        if cnt == 150:
            break

    predict = np.asarray(predict)
    real = np.asarray(real).reshape(cnt,3)
    fig = plt.figure(0)
    plt.title("x")
    plt.scatter(range(cnt),predict[:, 0], s = 0.3)
    plt.scatter(range(cnt),real[:, 0], s = 0.3, alpha= 0.5)
    plt.xlabel("count of batches")
    plt.ylabel("actions(0:move -;1:stay;2:move +")
    plt.legend(["pred","real"])
    fig = plt.figure(1)
    plt.title("y")
    plt.scatter(range(cnt), predict[:, 1], s = 0.3)
    plt.scatter(range(cnt), real[:, 1],s = 0.3,alpha= 0.5)
    plt.xlabel("count of batches")
    plt.ylabel("actions(0:move -;1:stay;2:move +")
    plt.legend(["pred", "real"])
    fig = plt.figure(2)
    plt.title("z")
    plt.scatter(range(cnt), predict[:, 2],s = 0.3)
    plt.scatter(range(cnt), real[:, 2],s = 0.3,alpha=0.5)
    plt.xlabel("count of batches")
    plt.ylabel("actions(0:move -;1:stay;2:move +")
    plt.legend(["pred", "real"])
    plt.show()
    # acc = cor / (cor + wrong)
    # print(acc)

def compute_loss_cee(pred, demo):
    """
    pred: # [batch, 3 * action_dims]
    demo: # [batch, action_dims]
    """
    batch_size = pred.size(0)
    space_dim = demo.size(-1)
    # [batch, 3, num_dims]
    pred = pred.reshape(batch_size, 3, space_dim)
    return torch.nn.CrossEntropyLoss(pred, demo)

def compute_loss_mse(pred, demo):
    """
    pred: # [batch, 3 * action_dims]
    demo: # [batch, action_dims]
    """
    batch_size = pred.size(0)
    space_dim = demo.size(-1)
    # [batch, 3, num_dims]
    pred = pred.reshape(batch_size, space_dim)
    return torch.nn.MSELoss(pred, demo)


if __name__ == "__main__":
    import configargparse

    p = configargparse.ArgParser()
    p.add("-c", "--config", is_config_file=True, default="conf/imi_learn_0218.yaml")
    p.add("--batch_size", default=8)
    p.add("--lr", default=0.001)
    p.add("--gamma", default=0.9)
    p.add("--period", default=3)
    p.add("--epochs", default=100)
    p.add("--resume", default=None)
    p.add("--num_workers", default=4, type=int)
    # model
    p.add("--embed_dim", required=True, type=int)
    p.add("--pretrained", required=True)
    p.add("--freeze_till", required=True, type=int)
    p.add("--action_dim", default=3, type=int)
    p.add("--num_heads", type=int)
    # data
    p.add("--train_csv", default="train.csv")
    p.add("--val_csv", default="val.csv")
    p.add("--num_stack", default=4, type=int)
    p.add("--frameskip", default=3, type=int)
    p.add("--loss_type", default="mse")

    args = p.parse_args()
    baselineRegValidate(args)