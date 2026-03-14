#include "plugin.hpp"


#ifdef METAMODULE_BUILTIN
extern Plugin* pluginInstance;
#else
Plugin* pluginInstance;
#endif

#ifndef METAMODULE
extern Model* modelBtfldTest;
#endif


#ifdef METAMODULE_BUILTIN
void init_schlappiengineering(Plugin* p) {
#else
void init(Plugin* p) {
#endif
	pluginInstance = p;

	// Add modules here
	// p->addModel(modelMyModule);
    p->addModel(modelBtfld);
    p->addModel(modelBTMX);
    p->addModel(modelNibbler);
#ifndef METAMODULE
    p->addModel(modelBtfldTest);
#endif

	// Any other plugin initialization may go here.
	// As an alternative, consider lazy-loading assets and lookup tables when your module is created to reduce startup times of Rack.
}
