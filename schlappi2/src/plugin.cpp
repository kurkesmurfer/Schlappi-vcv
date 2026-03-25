#include "plugin.hpp"

Plugin* pluginInstance;

void init(Plugin* p) {
	pluginInstance = p;
	p->addModel(modelBtfld);
	p->addModel(modelBTMX);
	p->addModel(modelNibbler);
}
