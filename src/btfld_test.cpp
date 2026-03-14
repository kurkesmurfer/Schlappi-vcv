// BTFLDtest — Quality comparison test module, VCVRack only.
// Pre-instantiates BTFLD DSP at 5 quality levels; switch between them
// at runtime via the Quality knob to find the minimum acceptable quality
// for the MetaModule port.
//
// Quality mapping:
//   0 = Q2  (16 taps — current MM minimum, aliased)
//   1 = Q4  (32 taps — current MM target)
//   2 = Q6  (48 taps)
//   3 = Q8  (64 taps)
//   4 = Q12 (96 taps — VCVRack default)
//
// Note: expect a brief click/transient when switching quality.

#ifndef METAMODULE

#include "plugin.hpp"
#include <cmath>
#include <array>

#define BTFLD_TEST_RATE 8

// ── Shared utilities (duplicated from btfld.cpp) ─────────────────────────────

struct ACCouplingFilterT {
    ACCouplingFilterT() : xPrev(0), yPrev(0), scalar(0) {}
    void setDecay(float halflife) { scalar = std::pow(2, -1.f / halflife); }
    float process(float x) {
        auto y = scalar * (x + yPrev - xPrev);
        yPrev = y; xPrev = x; return y;
    }
    float xPrev, yPrev, scalar;
};

struct BitCalculatorT {
    int shiftAmount = 0;
    int delayBeforeGoingHigh = BTFLD_TEST_RATE * 1.5f;
    int counter = 0;
    int lastOddValue = 0;

    bool oddTracker(int input) {
        if ((input % 2) == 0) { counter = 0; return false; }
        if (input != lastOddValue) { lastOddValue = input; counter = 1; }
        else if (counter < delayBeforeGoingHigh) { ++counter; }
        return counter >= delayBeforeGoingHigh;
    }
    float process(float input) {
        return oddTracker(static_cast<int>(input) >> shiftAmount) ? 1.f : 0.f;
    }
};

// ── Filter bundle (one per quality level) ────────────────────────────────────

template<int Q>
struct FilterBundle {
    dsp::Upsampler<BTFLD_TEST_RATE, Q> inputUp{0.5f};
    dsp::Upsampler<BTFLD_TEST_RATE, Q> cvUp{0.5f};
    dsp::Upsampler<BTFLD_TEST_RATE, Q> injectUp{0.5f};
    std::array<dsp::Decimator<BTFLD_TEST_RATE, Q>, 4> bitDown;
    dsp::Decimator<BTFLD_TEST_RATE, Q> stepDown;
    dsp::Decimator<BTFLD_TEST_RATE, Q> sawDown;
    float upsamplerGain = 1.f;
    float downsamplerGain = 1.f;

    FilterBundle() {
        std::fill(bitDown.begin(), bitDown.end(), 0.8f);
        float ks = 0;
        for (int i = 0; i < BTFLD_TEST_RATE * Q; ++i) ks += cvUp.kernel[i];
        upsamplerGain = 1.f / ks;
        ks = 0;
        for (int i = 0; i < BTFLD_TEST_RATE * Q; ++i) ks += bitDown[0].kernel[i];
        downsamplerGain = 1.f / ks;
    }
};

// ── Module ────────────────────────────────────────────────────────────────────

struct BtfldTest : Module {
    enum ParamId {
        GAIN_PARAM, CV_PARAM, RANGE_PARAM, QUALITY_PARAM, PARAMS_LEN
    };
    enum InputId {
        INPUT_INPUT, CV_INPUT, INJECT_INPUT, INPUTS_LEN
    };
    enum OutputId {
        SAW_OUTPUT, BIT_OUTPUT, BIT_OUTPUT1, BIT_OUTPUT2, BIT_OUTPUT3,
        STEP_OUT_OUTPUT, OUTPUTS_LEN
    };
    enum LightId { LIGHTS_LEN };

    float feedback = 0.f;
    ACCouplingFilterT stepFilter, sawFilter;
    std::array<BitCalculatorT, 4> bitCalculators;

    // All 5 quality variants pre-instantiated
    FilterBundle<2>  b2;
    FilterBundle<4>  b4;
    FilterBundle<6>  b6;
    FilterBundle<8>  b8;
    FilterBundle<12> b12;

    std::array<float, BTFLD_TEST_RATE> upsampledInput{};
    std::array<float, BTFLD_TEST_RATE> upsampledCV{};
    std::array<float, BTFLD_TEST_RATE> upsampledInject{};
    std::array<float, BTFLD_TEST_RATE> workingBuffer{};
    std::array<float, BTFLD_TEST_RATE> upsampledStepOut{};
    std::array<float, BTFLD_TEST_RATE> upsampledSaw{};

    struct QualityQuantity : ParamQuantity {
        static constexpr const char* labels[] = {
            "Q2 — MM minimum (aliased)",
            "Q4 — MM target",
            "Q6",
            "Q8",
            "Q12 — VCVRack default"
        };
        std::string getDisplayValueString() override {
            int q = (int)(getValue() + 0.5f);
            q = std::max(0, std::min(4, q));
            return labels[q];
        }
    };

    BtfldTest() {
        config(PARAMS_LEN, INPUTS_LEN, OUTPUTS_LEN, LIGHTS_LEN);
        configParam(GAIN_PARAM, 0.f, 2.f, 1.f, "Gain");
        configParam(CV_PARAM, 0.f, 1.f, 0.f, "Gain CV");
        configParam(RANGE_PARAM, 0.f, 1.f, 0.f, "Range (+10/±5)");
        configParam<QualityQuantity>(QUALITY_PARAM, 0.f, 4.f, 1.f, "Quality");
        paramQuantities[QUALITY_PARAM]->snapEnabled = true;
        configInput(INPUT_INPUT, "In");
        configInput(CV_INPUT, "CV");
        configInput(INJECT_INPUT, "Inject");
        configOutput(SAW_OUTPUT, "Saw");
        configOutput(BIT_OUTPUT,  "Bit 1");
        configOutput(BIT_OUTPUT1, "Bit 2");
        configOutput(BIT_OUTPUT2, "Bit 4");
        configOutput(BIT_OUTPUT3, "Bit 8");
        configOutput(STEP_OUT_OUTPUT, "Step");
        bitCalculators[0].shiftAmount = 0;
        bitCalculators[1].shiftAmount = 1;
        bitCalculators[2].shiftAmount = 2;
        bitCalculators[3].shiftAmount = 3;
    }

    void onSampleRateChange(const SampleRateChangeEvent& e) override {
        stepFilter.setDecay(0.25f * e.sampleRate);
        sawFilter.setDecay(0.25f * e.sampleRate);
    }

    float saturate(float x) { return std::min(std::max(0.f, x), 11.7f); }

    template<int Q>
    void processBundle(FilterBundle<Q>& b) {
        auto cvInput = inputs[CV_INPUT].isConnected() ? inputs[CV_INPUT].getVoltage() : feedback;
        auto gain = params[GAIN_PARAM].getValue() + params[CV_PARAM].getValue() * cvInput * 0.1f;
        b.cvUp.process(gain * b.upsamplerGain, upsampledCV.data());

        auto inputSignal = inputs[INPUT_INPUT].isConnected() ? inputs[INPUT_INPUT].getVoltage() : 0.f;
        auto bipolar = params[RANGE_PARAM].getValue() > 0.5f;

        if (inputs[INPUT_INPUT].isConnected())
            b.inputUp.process(inputSignal * b.upsamplerGain, upsampledInput.data());
        else
            upsampledInput.fill(0.f);

        if (inputs[INJECT_INPUT].isConnected()) {
            auto inject = inputs[INJECT_INPUT].getVoltage();
            b.injectUp.process(inject * b.upsamplerGain, upsampledInject.data());
        } else {
            upsampledInject.fill(0.f);
        }

        for (int ss = 0; ss < BTFLD_TEST_RATE; ++ss) {
            upsampledInput[ss] *= upsampledCV[ss];
            upsampledInput[ss] += bipolar ? 5.f : 0.f;
            upsampledInput[ss] += upsampledInject[ss];
            upsampledInput[ss] = saturate(upsampledInput[ss]);
            upsampledInput[ss] *= (16.f / 10.f);
            upsampledStepOut[ss] = std::max(upsampledInput[ss] - 15.99f, 0.f);
            upsampledInput[ss] = std::min(upsampledInput[ss], 15.99f);
            upsampledStepOut[ss] += std::floor(upsampledInput[ss]);
            upsampledSaw[ss] = std::min(std::max(0.f, upsampledInput[ss] - upsampledStepOut[ss]), 1.1f);
        }

        for (int b_ = 0; b_ < 4; ++b_) {
            for (int ss = 0; ss < BTFLD_TEST_RATE; ++ss)
                workingBuffer[ss] = bitCalculators[b_].process(upsampledInput[ss]);
            float volt = b.bitDown[b_].process(workingBuffer.data()) * b.downsamplerGain;
            outputs[BIT_OUTPUT + b_].setVoltage(volt * 10.f - (bipolar ? 5.f : 0.f));
        }

        float steps = b.stepDown.process(upsampledStepOut.data()) * b.downsamplerGain;
        float saw   = b.sawDown.process(upsampledSaw.data())   * b.downsamplerGain;

        saw *= 10.f;
        float rescaledSteps = steps * (10.f / 16.f);
        outputs[STEP_OUT_OUTPUT].setVoltage(bipolar ? stepFilter.process(rescaledSteps) : rescaledSteps);
        float filteredSaw = sawFilter.process(saw);
        feedback = std::min(std::max(-12.f, bipolar ? filteredSaw : saw), 12.f);
        outputs[SAW_OUTPUT].setVoltage(feedback);
    }

    void process(const ProcessArgs& args) override {
        int q = (int)(params[QUALITY_PARAM].getValue() + 0.5f);
        switch (q) {
            case 0: processBundle(b2);  break;
            case 1: processBundle(b4);  break;
            case 2: processBundle(b6);  break;
            case 3: processBundle(b8);  break;
            default: processBundle(b12); break;
        }
    }
};

// ── Widget ────────────────────────────────────────────────────────────────────

struct BtfldTestWidget : ModuleWidget {
    BtfldTestWidget(BtfldTest* module) {
        setModule(module);
        // Plain panel — test tool only
        box.size = Vec(8 * RACK_GRID_WIDTH, RACK_GRID_HEIGHT);
        auto* panel = new rack::app::SvgPanel;
        panel->box.size = box.size;
        addChild(panel);

        // Screws
        addChild(createWidget<ThemedScrew>(Vec(RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ThemedScrew>(Vec(box.size.x - 2*RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ThemedScrew>(Vec(RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ThemedScrew>(Vec(box.size.x - 2*RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        // Params — same positions as BTFLD, quality knob added top-right
        addParam(createParamCentered<RoundBlackKnob>(mm2px(Vec(15.22, 16.406)), module, BtfldTest::GAIN_PARAM));
        addParam(createParamCentered<RoundBlackKnob>(mm2px(Vec(15.22, 41.785)), module, BtfldTest::CV_PARAM));
        addParam(createParamCentered<CKSS>(mm2px(Vec(7.217, 58.613)), module, BtfldTest::RANGE_PARAM));
        addParam(createParamCentered<RoundLargeBlackKnob>(mm2px(Vec(28.0, 20.0)), module, BtfldTest::QUALITY_PARAM));

        // Inputs
        addInput(createInputCentered<PJ301MPort>(mm2px(Vec(7.196, 72.886)),  module, BtfldTest::INPUT_INPUT));
        addInput(createInputCentered<PJ301MPort>(mm2px(Vec(7.196, 85.892)),  module, BtfldTest::CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(mm2px(Vec(7.196, 98.729)),  module, BtfldTest::INJECT_INPUT));

        // Outputs
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(20.541, 60.048)),  module, BtfldTest::SAW_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(20.541, 72.886)),  module, BtfldTest::BIT_OUTPUT3));
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(20.541, 85.892)),  module, BtfldTest::BIT_OUTPUT2));
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(20.539, 98.809)),  module, BtfldTest::BIT_OUTPUT1));
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(20.541, 111.736)), module, BtfldTest::BIT_OUTPUT));
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(7.196,  111.736)), module, BtfldTest::STEP_OUT_OUTPUT));
    }
};

Model* modelBtfldTest = createModel<BtfldTest, BtfldTestWidget>("BTFLDtest");

#endif // METAMODULE
