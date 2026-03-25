RACK_DIR ?= ../..

# Include path for plugin.hpp and shared headers
FLAGS += -I../src

# Enable MetaModule-optimised DSP paths for VCVRack comparison
CXXFLAGS += -DNIBBLER_BASE_RATE

SOURCES += src/plugin.cpp
SOURCES += ../src/btfld.cpp
SOURCES += ../src/btmx.cpp
SOURCES += ../src/nibbler.cpp

DISTRIBUTABLES += res
DISTRIBUTABLES += $(wildcard LICENSE*)

include $(RACK_DIR)/plugin.mk
