import sys

from plenum.test.restart.helper import restart_nodes
from plenum.test.stasher import delay_rules

from plenum.server.quorums import Quorum

from stp_core.loop.eventually import eventually

from plenum.test.delayers import cDelay, pDelay, ppDelay
from plenum.test.helper import sdk_send_batches_of_random_and_check, \
    sdk_send_batches_of_random

from plenum.test.checkpoints.conftest import chkFreqPatched, reqs_for_checkpoint

CHK_FREQ = 5
LOG_SIZE = 3 * CHK_FREQ

req_num = CHK_FREQ * 4
howlong = 100
ledger_id = 1
another_key = 'request_2'


def node_caughtup(node, old_count):
    assert node.spylog.count(node.allLedgersCaughtUp) > old_count


def test_clearing_forwarded_preprepared_request(
        looper, chkFreqPatched, reqs_for_checkpoint, txnPoolNodeSet,
        sdk_pool_handle, sdk_wallet_steward):
    # Case when backup ordered correctly, but primary had problems.
    # As a result, master will execute caughtup txns and will be removed
    # from requests queues
    behind_node = txnPoolNodeSet[-1]

    sdk_send_batches_of_random_and_check(looper, txnPoolNodeSet, sdk_pool_handle,
                                         sdk_wallet_steward, CHK_FREQ, CHK_FREQ)
    with delay_rules(behind_node.nodeIbStasher,
                     pDelay(delay=sys.maxsize, instId=0),
                     cDelay(delay=sys.maxsize, instId=0)):
        count = behind_node.spylog.count(behind_node.allLedgersCaughtUp)

        sdk_send_batches_of_random(looper, txnPoolNodeSet, sdk_pool_handle,
                                   sdk_wallet_steward, req_num, req_num)

        looper.run(eventually(node_caughtup, behind_node, count, retryWait=1))

    assert all(r.executed and r.forwardedTo == 0 for r in behind_node.requests.values())


def test_freeing_forwarded_preprepared_request(
        looper, chkFreqPatched, reqs_for_checkpoint, txnPoolNodeSet,
        sdk_pool_handle, sdk_wallet_steward):
    # Case, when both backup and primary had problems
    behind_node = txnPoolNodeSet[-1]

    sdk_send_batches_of_random_and_check(looper, txnPoolNodeSet, sdk_pool_handle,
                                         sdk_wallet_steward, CHK_FREQ, CHK_FREQ)
    with delay_rules(behind_node.nodeIbStasher,
                     pDelay(delay=sys.maxsize),
                     cDelay(delay=sys.maxsize)):
        count = behind_node.spylog.count(behind_node.allLedgersCaughtUp)

        sdk_send_batches_of_random(looper, txnPoolNodeSet, sdk_pool_handle,
                                   sdk_wallet_steward, req_num, req_num)

        looper.run(eventually(node_caughtup, behind_node, count, retryWait=1))

    assert len(behind_node.requests) == req_num
    assert all(r.executed for r in behind_node.requests.values() if behind_node.seqNoDB.get(r.request.key)[1])

    sdk_send_batches_of_random_and_check(looper, txnPoolNodeSet, sdk_pool_handle,
                                         sdk_wallet_steward, CHK_FREQ, CHK_FREQ)

    # Master and backup replicas do not stash new requests and succesfully order them
    assert len(behind_node.requests) == req_num


def test_freeing_forwarded_not_preprepared_request(
        looper, chkFreqPatched, reqs_for_checkpoint, txnPoolNodeSet,
        sdk_pool_handle, sdk_wallet_steward, tconf, tdir, allPluginsPath):
    behind_node = txnPoolNodeSet[-1]
    restart_nodes(looper, txnPoolNodeSet, [behind_node], tconf, tdir, allPluginsPath)
    behind_node = txnPoolNodeSet[-1]

    sdk_send_batches_of_random_and_check(looper, txnPoolNodeSet, sdk_pool_handle,
                                         sdk_wallet_steward, CHK_FREQ, CHK_FREQ)
    with delay_rules(behind_node.nodeIbStasher,
                     ppDelay(delay=sys.maxsize),
                     pDelay(delay=sys.maxsize),
                     cDelay(delay=sys.maxsize)):
        count = behind_node.spylog.count(behind_node.allLedgersCaughtUp)
        sdk_send_batches_of_random(looper, txnPoolNodeSet, sdk_pool_handle,
                                   sdk_wallet_steward, req_num, req_num)
        looper.run(eventually(node_caughtup, behind_node, count, retryWait=1))

    # We execute caughtup requests
    assert len(behind_node.requests) == req_num
    assert all(r.executed for r in behind_node.requests.values() if behind_node.seqNoDB.get(r.request.key)[1])


def test_deletion_non_forwarded_request(
        looper, chkFreqPatched, reqs_for_checkpoint, txnPoolNodeSet,
        sdk_pool_handle, sdk_wallet_steward, tconf, tdir, allPluginsPath):
    master_node = txnPoolNodeSet[0]
    behind_node = txnPoolNodeSet[-1]

    restart_nodes(looper, txnPoolNodeSet, [behind_node], tconf, tdir, allPluginsPath)
    behind_node = txnPoolNodeSet[-1]

    sdk_send_batches_of_random_and_check(looper, txnPoolNodeSet, sdk_pool_handle,
                                         sdk_wallet_steward, CHK_FREQ, CHK_FREQ)
    behind_node.quorums.propagate = Quorum(len(txnPoolNodeSet) + 1)

    with delay_rules(behind_node.nodeIbStasher,
                     ppDelay(delay=sys.maxsize),
                     pDelay(delay=sys.maxsize),
                     cDelay(delay=sys.maxsize)):
        count = behind_node.spylog.count(behind_node.allLedgersCaughtUp)
        sdk_send_batches_of_random(looper, txnPoolNodeSet, sdk_pool_handle,
                                   sdk_wallet_steward, req_num, req_num)
        looper.run(eventually(node_caughtup, behind_node, count, retryWait=1))

    # We clear caughtup requests
    assert all(r.executed and r.forwardedTo == 0 for r in behind_node.requests.values())
