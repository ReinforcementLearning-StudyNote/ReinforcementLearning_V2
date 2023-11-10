import os
import sys
import datetime
import time
import cv2 as cv
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.distributions import Normal

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../../")
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/../")

from SecondOrderIntegration import SecondOrderIntegration
from environment.color import Color
from algorithm.policy_base.Proximal_Policy_Optimization2 import Proximal_Policy_Optimization2 as PPO2
from utils.functions import *
from utils.classes import Normalization

timestep = 0
ENV = 'SecondOrderIntegration'
ALGORITHM = 'PPO2'
test_episode = []
test_reward = []
sumr_list = []


class PPOActor_Gaussian(nn.Module):
	def __init__(self,
				 state_dim: int = 3,
				 action_dim: int = 3,
				 a_min: np.ndarray = np.zeros(3),
				 a_max: np.ndarray = np.ones(3),
				 init_std: float = 0.5,
				 use_orthogonal_init: bool = True):
		super(PPOActor_Gaussian, self).__init__()
		# self.fc1 = nn.Linear(state_dim, 128)
		# self.fc2 = nn.Linear(128, 128)
		# self.fc3 = nn.Linear(128, 64)
		# self.mean_layer = nn.Linear(64, action_dim)
		self.fc1 = nn.Linear(state_dim, 8)
		self.fc2 = nn.Linear(8, 8)
		self.mean_layer = nn.Linear(8, action_dim)
		self.activate_func = nn.Tanh()
		self.a_min = torch.tensor(a_min, dtype=torch.float)
		self.a_max = torch.tensor(a_max, dtype=torch.float)
		self.off = (self.a_min + self.a_max) / 2.0
		self.gain = self.a_max - self.off
		self.action_dim = action_dim
		self.std = torch.tensor(init_std, dtype=torch.float)

		if use_orthogonal_init:
			self.orthogonal_init_all()

	@staticmethod
	def orthogonal_init(layer, gain=1.0):
		nn.init.orthogonal_(layer.weight, gain=gain)
		nn.init.constant_(layer.bias, 0)

	def orthogonal_init_all(self):
		self.orthogonal_init(self.fc1)
		self.orthogonal_init(self.fc2)
		# self.orthogonal_init(self.fc3)
		self.orthogonal_init(self.mean_layer, gain=0.01)

	def forward(self, s):
		s = self.activate_func(self.fc1(s))
		s = self.activate_func(self.fc2(s))
		# s = self.activate_func(self.fc3(s))
		mean = torch.tanh(self.mean_layer(s)) * self.gain + self.off
		# mean = torch.relu(self.mean_layer(s))
		return mean

	def get_dist(self, s):
		mean = self.forward(s)
		std = self.std.expand_as(mean)
		dist = Normal(mean, std)
		return dist

	def evaluate(self, state):
		with torch.no_grad():
			t_state = torch.unsqueeze(torch.tensor(state, dtype=torch.float), 0)
			action_mean = self.forward(t_state)
		return action_mean.detach().cpu().numpy().flatten()


class PPOCritic(nn.Module):
	def __init__(self, state_dim=3, use_orthogonal_init: bool = True):
		super(PPOCritic, self).__init__()
		# self.fc1 = nn.Linear(state_dim, 128)
		# self.fc2 = nn.Linear(128, 128)
		# self.fc3 = nn.Linear(128, 32)
		# self.fc4 = nn.Linear(32, 1)
		self.fc1 = nn.Linear(state_dim, 8)
		self.fc2 = nn.Linear(8, 8)
		self.fc3 = nn.Linear(8, 1)
		self.activate_func = nn.Tanh()

		if use_orthogonal_init:
			self.orthogonal_init_all()

	@staticmethod
	def orthogonal_init(layer, gain=1.0):
		nn.init.orthogonal_(layer.weight, gain=gain)
		nn.init.constant_(layer.bias, 0)

	def orthogonal_init_all(self):
		self.orthogonal_init(self.fc1)
		self.orthogonal_init(self.fc2)
		self.orthogonal_init(self.fc3)
		# self.orthogonal_init(self.fc4)

	def forward(self, s):
		s = self.activate_func(self.fc1(s))
		s = self.activate_func(self.fc2(s))
		# s = self.activate_func(self.fc3(s))
		v_s = self.fc3(s)
		return v_s

	def init(self, use_orthogonal_init):
		if use_orthogonal_init:
			self.orthogonal_init_all()
		else:
			self.fc1.reset_parameters()
			self.fc2.reset_parameters()
			self.fc3.reset_parameters()


if __name__ == '__main__':
	log_dir = os.path.dirname(os.path.abspath(__file__)) + '/datasave/log/'
	if not os.path.exists(log_dir):
		os.makedirs(log_dir)
	simulationPath = log_dir + datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d-%H-%M-%S') + '-' + ALGORITHM + '-' + ENV + '/'
	os.mkdir(simulationPath)
	c = cv.waitKey(1)

	RETRAIN = False

	env = SecondOrderIntegration()
	reward_norm = Normalization(shape=1)
	env_msg = {'state_dim': env.state_dim, 'action_dim': env.action_dim, 'name': env.name, 'action_range': env.action_range}
	t_epoch = 0  # 当前训练次数
	test_num = 0
	sumr = 0.
	buffer_index = 0
	ppo_msg = {'gamma': 0.99,
			   'K_epochs': 200,
			   'eps_clip': 0.2,
			   'buffer_size': int(env.time_max / env.dt) * 2,
			   'state_dim': env.state_dim,
			   'action_dim': env.action_dim,
			   'a_lr': 1e-4,
			   'c_lr': 1e-3,
			   'set_adam_eps': True,
			   'lmd': 0.95,
			   'use_adv_norm': True,
			   'mini_batch_size': 64,
			   'entropy_coef': 0.01,
			   'use_grad_clip': True,
			   'use_lr_decay': True,
			   'max_train_steps': int(5e6),
			   'using_mini_batch': False}

	agent = PPO2(env_msg=env_msg,
				 ppo_msg=ppo_msg,
				 actor=PPOActor_Gaussian(state_dim=env.state_dim,
										 action_dim=env.action_dim,
										 a_min=np.array(env.action_range)[:, 0],
										 a_max=np.array(env.action_range)[:, 1],
										 init_std=0.8,
										 use_orthogonal_init=True),
				 critic=PPOCritic(state_dim=env.state_dim, use_orthogonal_init=True))
	agent.PPO2_info()

	if RETRAIN:
		print('RELOADING......')
		'''如果两次奖励函数不一样，那么必须重新初始化 critic'''
		# optPath = os.path.dirname(os.path.abspath(__file__)) + '/../datasave/nets/train_opt/trainNum_300_episode_2/'
		optPath = os.path.dirname(os.path.abspath(__file__)) + '/../datasave/nets/temp/'
		agent.actor.load_state_dict(torch.load(optPath + 'actor_trainNum_300'))  # 测试时，填入测试actor网络
		# agent.critic.load_state_dict(torch.load(optPath + 'critic_trainNum_300'))
		agent.critic.init(True)
		'''如果两次奖励函数不一样，那么必须重新初始化 critic'''

	env.is_terminal = True
	while True:
		'''1. 收集数据'''
		while buffer_index < agent.buffer.batch_size:
			if env.is_terminal:  # 如果某一个回合结束
				print('Sumr:  ', sumr)
				sumr_list.append(sumr)
				sumr = 0.
				env.reset(random=True)
			else:
				env.current_state = env.next_state.copy()
				s = env.current_state_norm(env.current_state, update=True)
				a, a_log_prob = agent.choose_action(s)
				env.step_update(a)
				# env.visualization()
				sumr += env.reward
				success = 0.0 if env.terminal_flag == 1 else 1.0	# 1 对应出界，固定时间内，不出界，就是 success
				agent.buffer.append(s=s,
									a=a,
									log_prob=a_log_prob,
									# r=reward_norm(env.reward),
									r=env.reward,
									s_=env.next_state_norm(env.next_state, update=True),
									done=1.0 if env.is_terminal else 0.0,
									success=success,
									index=buffer_index)
				buffer_index += 1
		'''1. 收集数据'''

		'''2. 学习'''
		print('~~~~~~~~~~ Training Start~~~~~~~~~~')
		print('Train Epoch: {}'.format(t_epoch))
		timestep += ppo_msg['buffer_size']
		agent.learn(timestep, buf_num=1)
		agent.cnt += 1
		buffer_index = 0
		'''2. 学习'''

		'''3. 每学习 10 次，测试一下'''
		if t_epoch % 10 == 0 and t_epoch > 0:
			n = 5
			print('   Training pause......')
			print('   Testing...')
			for i in range(n):
				env.reset(random=True)
				test_r = 0.
				while not env.is_terminal:
					env.current_state = env.next_state.copy()
					_a = agent.evaluate(env.current_state_norm(env.current_state, update=False))
					env.step_update(_a)
					test_r += env.reward
					env.visualization()
				test_num += 1
				test_reward.append(test_r)
				print('   Evaluating %.0f | Reward: %.2f ' % (i, test_r))
			pd.DataFrame({'reward': test_reward}).to_csv(simulationPath + 'test_record.csv')
			pd.DataFrame({'sumr_list': sumr_list}).to_csv(simulationPath + 'sumr_list.csv')
			print('   Testing finished...')
			print('   Go back to training...')
		'''3. 每学习 50 次，测试一下'''

		'''4. 每学习 250 次，减小一次探索概率'''
		if t_epoch % 250 == 0 and t_epoch > 0:
			if agent.actor.std > 0.1:
				agent.actor.std -= 0.05
		'''4. 每学习 100 次，减小一次探索概率'''

		'''5. 每学习 50 次，保存一下 policy'''
		if t_epoch % 10 == 0 and t_epoch > 0:
			# 	average_test_r = agent.agent_evaluate(5)
			test_num += 1
			print('...check point save...')
			temp = simulationPath + 'trainNum_{}/'.format(t_epoch)
			os.mkdir(temp)
			time.sleep(0.01)
			agent.save_ac(msg='', path=temp)
			env.save_state_norm(temp)
		'''5. 每学习 50 次，保存一下 policy'''

		t_epoch += 1
		print('~~~~~~~~~~  Training End ~~~~~~~~~~')
