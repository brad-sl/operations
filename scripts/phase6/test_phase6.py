#!/usr/bin/env python3
import pytest
import os
from unittest.mock import Mock, patch
from phase6 import Phase6Initializer

@pytest.fixture
def mock_cb_client():
    client = Mock()
    return client

@pytest.fixture
def mock_state():
    state = Mock()
    state.get_state.return_value = {}
    state.update_state = Mock()
    return state

@pytest.fixture
def mock_order_exec():
    exec_ = Mock()
    exec_.place_sl_tp = Mock()
    return exec_

def test_fresh_start(mock_cb_client, mock_state, mock_order_exec):
    mock_cb_client.get_account_history.return_value = []
    mock_state.get_state.return_value = {}

    with patch('os.environ', {'ENTER_TRADING_FIAT_USDC': 'USDC', 'ENTER_DEPLOY_BUDGET': '1000', 
                              'ESTIMATE_ENTRY_PRICE': '50000', 'LIQUIDATION_PRICE': '40000',
                              'SL_FROM_ENTRY': '2', 'TP_FROM_ENTRY': '4'}):
        initializer = Phase6Initializer(mock_cb_client, mock_state, mock_order_exec)
        initializer.run()

        state_after = mock_state.get_state.return_value
        assert state_after['scenario'] == 'fresh_start'
        assert state_after['status'] == 'READY_TO_TRADE'
        assert state_after['deploy_budget'] == 1000.0
        assert mock_order_exec.place_sl_tp.called

def test_takeover_2(mock_cb_client, mock_state, mock_order_exec):
    history = [{'price': 49000, 'status': 'open'}, {'price': 51000, 'status': 'open'}]
    mock_cb_client.get_account_history.return_value = history
    mock_state.get_state.return_value = {'balance': 2000}

    with patch('os.environ', {'SL_FROM_AVG_ENTRY': '2', 'TP_FROM_AVG_ENTRY': '4'}):
        initializer = Phase6Initializer(mock_cb_client, mock_state, mock_order_exec)
        initializer.run()

        state_after = mock_state.get_state.return_value
        assert state_after['scenario'] == 'takeover_2'
        assert state_after['status'] == 'READY_TO_TRADE'
        assert mock_order_exec.place_sl_tp.call_count == 2

def test_ready_start(mock_cb_client, mock_state, mock_order_exec):
    mock_cb_client.get_account_history.return_value = []
    mock_state.get_state.return_value = {'status': 'ready', 'deploy_budget': 1500, 'trading_fiat': 'USDT'}

    initializer = Phase6Initializer(mock_cb_client, mock_state, mock_order_exec)
    initializer.run()

    state_after = mock_state.get_state.return_value
    assert state_after['scenario'] == 'ready_start'
    assert state_after['status'] == 'READY_TO_TRADE'

if __name__ == '__main__':
    pytest.main(['-v', __file__])
