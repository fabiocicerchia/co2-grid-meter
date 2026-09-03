"""The Waveshare 2.13" B V4 tri-colour panel, as the vendor drives it.

Register writes and the SPI wiring, kept apart from the rendering in
`display.py` because the two change for entirely different reasons: this file
changes when the panel does, and the vendor's method names (`ReadBusy`,
`SetWindows`) are kept as they are so the reference driver stays diffable
against it.

Imported by bare module name, like every other module under pico/ — see
CLAUDE.md.
"""

import framebuf
import utime
from machine import SPI, Pin
from utils import log

EPD_WIDTH = 122
EPD_HEIGHT = 250
RST_PIN = 12
DC_PIN = 8
CS_PIN = 9
BUSY_PIN = 13


class EPD_2in13_B_V4_Base:
    def __init__(self):
        self.reset_pin = Pin(RST_PIN, Pin.OUT)

        self.busy_pin = Pin(BUSY_PIN, Pin.IN, Pin.PULL_UP)
        self.cs_pin = Pin(CS_PIN, Pin.OUT)
        if EPD_WIDTH % 8 == 0:
            self.width = EPD_WIDTH
        else:
            self.width = (EPD_WIDTH // 8) * 8 + 8
        self.height = EPD_HEIGHT

        self.spi = SPI(1)
        self.spi.init(baudrate=4000_000)
        self.dc_pin = Pin(DC_PIN, Pin.OUT)

        self.buffer_black = bytearray(self.height * self.width // 8)
        self.buffer_red = bytearray(self.height * self.width // 8)

    def init(self):
        log("Init e-ink")
        self.reset()

        self.ReadBusy()
        self.send_command(0x12)  # SWRESET
        self.ReadBusy()

        self.send_command(0x01)  # Driver output control
        self.send_data(0xF9)
        self.send_data(0x00)
        self.send_data(0x00)

        self.send_command(0x11)  # data entry mode
        self.send_data(self.command_code)

        self.SetWindows(0, 0, self.width - 1, self.height - 1)
        self.SetCursor(0, 0)

        self.send_command(0x3C)  # BorderWaveform
        self.send_data(0x05)

        self.send_command(0x18)  # Read built-in temperature sensor
        self.send_data(0x80)

        self.send_command(0x21)  #  Display update control
        self.send_data(0x80)
        self.send_data(0x80)

        self.ReadBusy()

        return 0

    def digital_write(self, pin, value):
        pin.value(value)

    def digital_read(self, pin):
        return pin.value()

    def delay_ms(self, delaytime):
        utime.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        self.spi.write(bytearray(data))

    def module_exit(self):
        self.digital_write(self.reset_pin, 0)

    # Hardware reset
    def reset(self):
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)
        self.digital_write(self.reset_pin, 0)
        self.delay_ms(2)
        self.digital_write(self.reset_pin, 1)
        self.delay_ms(50)

    def send_command(self, command):
        self.digital_write(self.dc_pin, 0)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([command])
        self.digital_write(self.cs_pin, 1)

    def send_data(self, data):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi_writebyte([data])
        self.digital_write(self.cs_pin, 1)

    def send_data1(self, buf):
        self.digital_write(self.dc_pin, 1)
        self.digital_write(self.cs_pin, 0)
        self.spi.write(bytearray(buf))
        self.digital_write(self.cs_pin, 1)

    def ReadBusy(self):
        while self.digital_read(self.busy_pin) == 1:
            self.delay_ms(10)
        self.delay_ms(20)

    def TurnOnDisplay(self):
        self.send_command(0x20)  # Activate Display Update Sequence
        self.ReadBusy()

    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        self.send_command(0x44)  # SET_RAM_X_ADDRESS_START_END_POSITION
        self.send_data((Xstart >> 3) & 0xFF)
        self.send_data((Xend >> 3) & 0xFF)

        self.send_command(0x45)  # SET_RAM_Y_ADDRESS_START_END_POSITION
        self.send_data(Ystart & 0xFF)
        self.send_data((Ystart >> 8) & 0xFF)
        self.send_data(Yend & 0xFF)
        self.send_data((Yend >> 8) & 0xFF)

    def SetCursor(self, Xstart, Ystart):
        self.send_command(0x4E)  # SET_RAM_X_ADDRESS_COUNTER
        self.send_data(Xstart & 0xFF)

        self.send_command(0x4F)  # SET_RAM_Y_ADDRESS_COUNTER
        self.send_data(Ystart & 0xFF)
        self.send_data((Ystart >> 8) & 0xFF)

    def Clear(self, colorblack, colorred):
        self.send_command(0x24)
        self.send_data1([colorblack] * self.height * int(self.width / 8))

        self.send_command(0x26)
        self.send_data1([colorred] * self.height * int(self.width / 8))

        self.TurnOnDisplay()

    def sleep(self):
        self.send_command(0x10)
        self.send_data(0x01)

        self.delay_ms(2000)
        self.module_exit()

    def display(self):
        self.send_command(0x24)
        for j in range(int(self.width / 8) - 1, -1, -1):
            for i in range(self.height):
                self.send_data(self.buffer_black[i + j * self.height])

        self.send_command(0x26)
        for j in range(int(self.width / 8) - 1, -1, -1):
            for i in range(self.height):
                self.send_data(self.buffer_red[i + j * self.height])

        self.TurnOnDisplay()


# TODO: TEST IT
class EPD_2in13_B_V4_Portrait(EPD_2in13_B_V4_Base):
    def __init__(self):
        super().__init__()

        self.command_code = 0x03

        self.imageblack = framebuf.FrameBuffer(
            self.buffer_black, self.width, self.height, framebuf.MONO_HLSB
        )
        self.imagered = framebuf.FrameBuffer(
            self.buffer_red, self.width, self.height, framebuf.MONO_HLSB
        )
        self.init()


class EPD_2in13_B_V4_Landscape(EPD_2in13_B_V4_Base):
    def __init__(self):
        super().__init__()

        self.command_code = 0x07

        self.imageblack = framebuf.FrameBuffer(
            self.buffer_black, self.height, self.width, framebuf.MONO_VLSB
        )
        self.imagered = framebuf.FrameBuffer(
            self.buffer_red, self.height, self.width, framebuf.MONO_VLSB
        )
        self.init()
