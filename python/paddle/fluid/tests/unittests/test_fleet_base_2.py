# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import tempfile
import unittest

import paddle

paddle.enable_static()

import os

import paddle.fluid as fluid


class TestFleetBase(unittest.TestCase):
    def setUp(self):
        os.environ["POD_IP"] = "127.0.0.1"
        os.environ["PADDLE_PORT"] = "36000"
        os.environ["PADDLE_TRAINERS_NUM"] = "1"
        # os.environ["PADDLE_PSERVERS_IP_PORT_LIST"] = \
        #    "127.0.0.1:36001,127.0.0.2:36001"

    def test_ps_minimize(self):
        import paddle
        import paddle.distributed.fleet as fleet

        os.environ["TRAINING_ROLE"] = "TRAINER"
        os.environ["PADDLE_TRAINER_ID"] = "1"

        input_x = paddle.static.data(name="x", shape=[-1, 32], dtype='float32')
        input_slot = paddle.static.data(
            name="slot", shape=[-1, 1], dtype='int64'
        )
        input_y = paddle.static.data(name="y", shape=[-1, 1], dtype='int64')

        emb = paddle.fluid.layers.embedding(
            input=input_slot, size=[10, 9], is_sparse=True
        )
        input_x = paddle.concat(x=[input_x, emb], axis=1)
        fc_1 = paddle.static.nn.fc(x=input_x, size=64, activation='tanh')
        fc_2 = paddle.static.nn.fc(x=fc_1, size=64, activation='tanh')
        prediction = paddle.static.nn.fc(x=[fc_2], size=2, activation='softmax')
        cost = paddle.nn.functional.cross_entropy(
            input=prediction, label=input_y, reduction='none', use_softmax=False
        )
        avg_cost = paddle.mean(x=cost)

        role = fleet.PaddleCloudRoleMaker(is_collective=False)
        fleet.init(role)

        strategy = paddle.distributed.fleet.DistributedStrategy()
        strategy.a_sync = False
        strategy.a_sync_configs = {"launch_barrier": False}

        optimizer = paddle.optimizer.SGD(learning_rate=0.001)
        optimizer = fleet.distributed_optimizer(optimizer, strategy=strategy)
        optimizer.minimize(avg_cost)

        place = fluid.CPUPlace()
        exe = fluid.Executor(place)
        exe.run(paddle.static.default_startup_program())
        compiled_prog = fluid.compiler.CompiledProgram(
            fluid.default_main_program()
        )

        temp_dir = tempfile.TemporaryDirectory()
        fleet.init_worker()
        fleet.fleet.save(
            dirname=temp_dir.name, feed=['x', 'y'], fetch=[avg_cost]
        )
        fleet.fleet.save(
            dirname=temp_dir.name, feed=[input_x, input_y], fetch=[avg_cost]
        )
        fleet.fleet.save(dirname=temp_dir.name)

        fleet.load_model(path=temp_dir.name, mode=0)
        fleet.load_model(path=temp_dir.name, mode=1)
        temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
