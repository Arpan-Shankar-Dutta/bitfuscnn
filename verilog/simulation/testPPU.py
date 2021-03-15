import cocotb
from cocotb.triggers import Timer
from cocotb.clock import Clock
import unittest


class PPUOutput:
    def __init__(self):
        pass


@cocotb.test()
def testPPU_1(dut):
    clk = dut.ppu.clk
    clk <= 0
    yield Timer(100, units="ns")
    clk <= 1
    yield Timer(100, units="ns")


@cocotb.coroutine
def reset_dut(ppu):
    ppu.reset_n <= 0
    yield Timer(100, units="ns")
    ppu.reset_n <= 1
    yield Timer(100, units="ns")


@cocotb.coroutine
def set_neighbor_data(ppu, neighbor_input, neighbor_cts, neighbor_exchange_done):
    for i in range(len(neighbor_input)):
        ppu.neighbor_input_value[i] <= neighbor_input[i][0]
        ppu.neighbor_input_row[i] <= neighbor_input[i][1]
        ppu.neighbor_input_column[i] <= neighbor_input[i][2]
        ppu.neighbor_cts[i] <= neighbor_cts[i]
        ppu.neighbor_exchange_done[i] <= neighbor_exchange_done[i]
        we_value = 1
        if neighbor_input[i][1] == -1:
            we_value = 0
        ppu.neighbor_input_write_enable[i] <= we_value
    yield Timer(1)


@cocotb.coroutine
def parley_oaram(ppu, oaram, oaram_indices):
    if ppu.oaram_write_enable.value:
        address = ppu.oaram_address.value
        oaram[address] = ppu.oaram_value.value
        if address > 0:
            oaram_indices[address - 1] = ppu.oaram_indices_value.value
    yield Timer(1)


def get_ppu_output(ppu, bank_count):
    ppu_output = PPUOutput()
    ppu_output.cycle_done = ppu.cycle_done.value
    ppu_output.clear_to_send = False
    if ppu.clear_to_send.value == 1:
        ppu_output.clear_to_send = True
    ppu_output.exchange_done = ppu.exchange_done.value
    ppu_output.buffer_outputs = []

    for i in range(bank_count):
        if ppu.buffer_write_enable[i].value == 0:
            new_value = (0, -1, -1, -1)
            ppu_output.buffer_outputs.append(new_value)
            continue
        value = ppu.buffer_data_write[i].value
        row = ppu.buffer_row_write[i].value
        column = ppu.buffer_column_write[i].value
        new_value = (value, row, column, 0)
        ppu_output.buffer_outputs.append(new_value)

    ppu_output.neighbor_outputs = []
    for i in range(8):
        val = ppu.neighbor_output_value[i].value
        row = ppu.neighbor_output_row[i].value
        column = ppu.neighbor_output_column[i].value
        write_enable = ppu.neighbor_output_write_enable[i].value
        if write_enable == 0:
            new_value = (0, -1, -1, -1)
            ppu_output.neighbor_outputs.append(new_value)
            continue
        new_value = (val, row, column, 0)
        ppu_output.append(new_value)

    return ppu_output


@cocotb.coroutine
def do_ppu(
    ppu,
    channel_group_done,
    oaram,
    oaram_indices,
    buffers,
    neighbor_inputs,
    neighbor_exchange_done,
    neighbor_cts,
):
    ppu.clk <= 0
    yield Timer(1)
    yield set_neighbor_data(ppu, neighbor_inputs, neighbor_cts, neighbor_exchange_done)
    ppu.clk <= 1
    yield Timer(1)
    yield parley_oaram(ppu, oaram, oaram_indices)
    ppu_output = get_ppu_output(ppu, 32)
    ppu.clk <= 0
    yield Timer(1)
    return ppu_output


def bank_from_rcc(row, column, channel, buffer_address_info):
    shift = row * 3
    shift = shift % buffer_address_info.buffer_count
    index = (column + shift) % buffer_address_info.buffer_count
    return int(index)


def entry_from_rcc(row, column, channel, buffer_address_info):
    return row


class BufferAddressInfo:
    def __init__(self, buffer_count, tile_size=4):
        self.buffer_count = buffer_count
        self.tile_size = tile_size


@cocotb.test()
def test_ppu_done_on_first_cycle(dut):
    tc = unittest.TestCase()
    ppu = dut.ppu
    yield reset_dut(ppu)
    RAM_SIZE = 1024
    BUFFER_COUNT = 32
    BUFFER_WIDTH = 32

    oaram = [0] * RAM_SIZE
    oaram_indices = [0] * RAM_SIZE
    back_buffers = [[0] * BUFFER_WIDTH] * BUFFER_COUNT
    neighbor_input = [(0, -1, -1, -1)] * 8
    neighbor_cts = [False] * 8
    neighbor_exchange_done = [False] * 8
    yield parley_oaram(ppu, oaram, oaram_indices)
    ppu_output = yield do_ppu(
        ppu,
        False,
        oaram,
        oaram_indices,
        back_buffers,
        neighbor_input,
        neighbor_exchange_done,
        neighbor_cts,
    )

    tc.assertTrue(ppu_output.clear_to_send)


@cocotb.test()
def test_ppu_saves_incoming_partial_sum(dut):
    tc = unittest.TestCase()
    ppu = dut.ppu
    yield reset_dut(ppu)

    RAM_SIZE = 1024
    BUFFER_COUNT = 32
    BUFFER_WIDTH = 32
    buffer_info = BufferAddressInfo(BUFFER_COUNT)

    oaram = [0] * RAM_SIZE
    oaram_indices = [0] * RAM_SIZE
    back_buffers = [[0] * BUFFER_WIDTH] * BUFFER_COUNT
    neighbor_input = [(3, 1, 1, 0)] + [(0, -1, -1, -1)] * 7
    neighbor_cts = [False] * 8
    neighbor_exchange_done = [False] * 8
    ppu_outputs = yield do_ppu(
        ppu,
        False,
        oaram,
        oaram_indices,
        back_buffers,
        neighbor_input,
        neighbor_exchange_done,
        neighbor_cts,
    )

    expected_buffer_outputs = [(0, -1, -1, -1)] * BUFFER_COUNT
    expected_buffer_outputs[bank_from_rcc(1, 1, 0, buffer_info)] = (3, 1, 1, 0)
    tc.assertEqual(ppu_outputs.buffer_outputs, expected_buffer_outputs)

@cocotb.test()
def test_has_leftover_inputs(dut):
    tc = unittest.TestCase()
    ppu = dut.ppu
    neighbor_input_processor = ppu.neighbor_input_processor
    RAM_SIZE = 1024
    BUFFER_COUNT = 32
    BUFFER_WIDTH = 32
    neighbor_input_processor.clk <= 0

    yield reset_dut(neighbor_input_processor)

    neighbor_input_processor.proc_neighbor_input_write_enable[0] <= 1
    neighbor_input_processor.proc_neighbor_input_value[0] <= 2
    neighbor_input_processor.proc_neighbor_input_row[0] <= 1
    neighbor_input_processor.proc_neighbor_input_column[0] <= 1

    yield Timer(1)
    tc.assertTrue(neighbor_input_processor.leftover_inputs.value)

    neighbor_input_processor.clk <= 1
    yield Timer(1)

    tc.assertFalse(neighbor_input_processor.leftover_inputs.value)

@cocotb.test()
def test_ppu_saves_sets_cts_false_when_conflicting_bank(dut):
    tc = unittest.TestCase()
    ppu = dut.ppu
    RAM_SIZE = 1024
    BUFFER_COUNT = 32
    BUFFER_WIDTH = 32
    buffer_info = BufferAddressInfo(BUFFER_COUNT)
    yield reset_dut(ppu)

    oaram = [0] * RAM_SIZE
    oaram_indices = [0] * RAM_SIZE
    back_buffers = [[0] * BUFFER_WIDTH] * BUFFER_COUNT
    neighbor_input = [(3, 1, 1, 0), (1, 1, 1, 0)] + [(0, -1, -1, -1)] * 6
    neighbor_cts = [False] * 8
    neighbor_exchange_done = [False] * 8
    ppu_output = yield do_ppu(
        ppu,
        False,
        oaram,
        oaram_indices,
        back_buffers,
        neighbor_input,
        neighbor_exchange_done,
        neighbor_cts
    )
    tc.assertFalse(ppu_output.cycle_done)
    tc.assertFalse(ppu_output.clear_to_send)

    expected_buffer_outputs = [(0, -1, -1, -1)] * BUFFER_COUNT
    expected_buffer_outputs[bank_from_rcc(1, 1, 1, buffer_info)] = (3, 1, 1, 0)
    tc.assertEqual(ppu_output.buffer_outputs, expected_buffer_outputs)

    ppu_output = yield do_ppu(
        ppu,
        False,
        oaram,
        oaram_indices,
        back_buffers,
        neighbor_input,
        neighbor_exchange_done,
        neighbor_cts
    )

    tc.assertTrue(ppu_output.clear_to_send)

    expected_buffer_outputs = [(0, -1, -1, -1)] * BUFFER_COUNT
    expected_buffer_outputs[bank_from_rcc(1, 1, 1, buffer_info)] = (1, 1, 1, 0)
    tc.assertEqual(ppu_output.buffer_outputs, expected_buffer_outputs)

