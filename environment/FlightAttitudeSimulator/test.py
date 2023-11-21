from FlightAttitudeSimulator import Flight_Attitude_Simulator
import cv2 as cv
import numpy as np


if __name__ == '__main__':
    env = Flight_Attitude_Simulator()
    video = cv.VideoWriter(env.name + '.mp4', cv.VideoWriter_fourcc(*"mp4v"), 60, (env.width, env.height))
    n = 2
    for i in range(n):
        env.reset(True)
        test_r = 0.
        while not env.is_terminal:
            a = np.random.uniform(env.action_range[:, 0], env.action_range[:, 1])
            env.step_update(a)
            test_r += env.reward
            env.visualization()
            video.write(env.image)
        print('   Evaluating %.0f | Reward: %.2f ' % (i, test_r))
    video.release()