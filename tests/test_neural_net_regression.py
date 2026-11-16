import numpy as np
import pytest

from src.machine_learning.neural_net import NeuralNetwork


def test_gradient_check_includes_l2_consistently():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(12, 3))
    y = rng.integers(0, 2, size=12).astype(float)
    net = NeuralNetwork([3, 5, 3, 1], learning_rate=0.003, l2=0.07, seed=19)

    result = net.gradient_check(X, y, eps=1e-5, n_checks=80, seed=5)

    assert result["max_relative_error"] < 1e-5


def test_network_supports_two_hidden_layers_and_counts_parameters():
    net = NeuralNetwork([14, 32, 16, 1], l2=1e-3)

    assert net.n_parameters() == (14 * 32 + 32) + (32 * 16 + 16) + (16 + 1)


def test_fit_rejects_invalid_labels():
    net = NeuralNetwork([2, 4, 1])
    X = np.ones((4, 2))

    with pytest.raises(ValueError, match="rótulos binários"):
        net.fit(X, np.array([0, 1, 2, 0]), epochs=1)


def test_fit_rejects_unknown_optimizer():
    net = NeuralNetwork([2, 4, 1])

    with pytest.raises(ValueError, match="optimizer"):
        net.fit(np.ones((4, 2)), np.array([0, 1, 0, 1]), optimizer="rmsprop", epochs=1)
