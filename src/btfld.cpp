#include "plugin.hpp"
#include "widgets/schlappi_widgets.hpp"
#include <cmath>
#include <array>

#define NIBBLE 4

struct ACCouplingFilter {
    ACCouplingFilter() : xPrev(0), yPrev(0), scalar(0) {}

    void setDecay(float halflife) {
        scalar = std::pow(2, -1.f / halflife);
    }

    float process(float x) {
        auto y = scalar * (x + yPrev - xPrev);
        yPrev = y;
        xPrev = x;
        return y;
    }
public:
    float xPrev, yPrev, scalar;
};

#if defined(METAMODULE) || defined(BTFLD_BASE_RATE)

struct OnePoleLP {
    OnePoleLP() : y(0), alpha(0) {}

    void setCutoff(float fc, float sampleRate) {
        alpha = std::exp(-2.f * M_PI * fc / sampleRate);
    }

    float process(float x) {
        y = (1.f - alpha) * x + alpha * y;
        return y;
    }
public:
    float y, alpha;
};

// Antiderivative of frac(1.6·v) with respect to v.
// f(v) = frac(1.6v),  F(v) = (r² + n) × 0.3125
// where s = 1.6v, n = floor(s), r = s - n.
// F is continuous and piecewise-quadratic across all fold boundaries.
static inline float adaa_antideriv(float v) {
    float s = 1.6f * v;
    float n = floorf(s);
    float r = s - n;
    return (r * r + n) * 0.3125f;
}

#else // original oversampled path

#define BTFLD_UPSAMPLE_RATE 8
#define BTFLD_UPSAMPLE_QUALITY 12

struct BitCalculator {
    int shiftAmount;
    int delayBeforeGoingHigh = BTFLD_UPSAMPLE_RATE * 1.5f;
    int counter;
    int lastOddValue;

    BitCalculator() {
        counter = 0;
        lastOddValue = 0;
    }

    bool oddTracker(int input) {
        if ((input % 2) == 0) {
            counter = 0;
            return false;
        }

        if (input != lastOddValue) {
            lastOddValue = input;
            counter = 1;
        } else if (counter < delayBeforeGoingHigh) {
            ++counter;
        }
        return counter >= delayBeforeGoingHigh;
    }

    float process(float input) {
        if (oddTracker(static_cast<int>(input) >> shiftAmount)) {
            return static_cast<float>(1.f);
        }
        return 0.f;
    }
};

#endif

struct Btfld : Module {
	enum ParamId {
		GAIN_PARAM,
		CV_PARAM,
		RANGE_PARAM,
		PARAMS_LEN
	};
	enum InputId {
		INPUT_INPUT,
		CV_INPUT,
		INJECT_INPUT,
		INPUTS_LEN
	};
	enum OutputId {
		SAW_OUTPUT,
        ENUMS(BIT_OUTPUT, NIBBLE),
        STEP_OUT_OUTPUT,
		OUTPUTS_LEN
	};
	enum LightId {
        ENUMS(LEVEL_LIGHT, 8),
		ENUMS(SAW_INDICATOR_LIGHT, 3),
		ENUMS(INPUT_INDICATOR_LIGHT, 3),
		ENUMS(CV_INDICATOR_LIGHT, 3),
        ENUMS(INJECT_INDICATOR_LIGHT, 3),
        ENUMS(BIT_INDICATOR_LIGHT, NIBBLE),
        STEP_INDICATOR_LIGHT,
		LIGHTS_LEN
	};

    float feedback = 0.f;
    ACCouplingFilter stepFilter;
    ACCouplingFilter sawFilter;

    int lightDivider = 0;
    static constexpr int LIGHT_DIVIDER = 256;

#if defined(METAMODULE) || defined(BTFLD_BASE_RATE)

    float v_prev = 0.f;
    float F_prev = 0.f;
    OnePoleLP sawLP;
    OnePoleLP stepLP;

#else // original oversampled path

    float previousInputSignal = 0.f;
    int previousSteps = 0;
    std::array<float, NIBBLE> bits = {};
    std::array<float, NIBBLE> bitFilter = {};

    dsp::Upsampler<BTFLD_UPSAMPLE_RATE, BTFLD_UPSAMPLE_QUALITY> inputUpsampler{0.5f};
    dsp::Upsampler<BTFLD_UPSAMPLE_RATE, BTFLD_UPSAMPLE_QUALITY> cvUpsampler{0.5f};
    dsp::Upsampler<BTFLD_UPSAMPLE_RATE, BTFLD_UPSAMPLE_QUALITY> injectUpsampler{0.5f};

    std::array<float, BTFLD_UPSAMPLE_RATE> upsampledInput = {};
    std::array<float, BTFLD_UPSAMPLE_RATE> upsampledCV = {};
    std::array<float, BTFLD_UPSAMPLE_RATE> upsampledInject = {};
    std::array<float, BTFLD_UPSAMPLE_RATE> workingBuffer = {};
    std::array<float, BTFLD_UPSAMPLE_RATE> upsampledStepOut = {};
    std::array<float, BTFLD_UPSAMPLE_RATE> upsampledSaw = {};

    std::array<dsp::Decimator<BTFLD_UPSAMPLE_RATE, BTFLD_UPSAMPLE_QUALITY>, 4> downsamplers;
    dsp::Decimator<BTFLD_UPSAMPLE_RATE, BTFLD_UPSAMPLE_QUALITY> stepDownsampler;
    dsp::Decimator<BTFLD_UPSAMPLE_RATE, BTFLD_UPSAMPLE_QUALITY> sawDownsampler;

    std::array<BitCalculator, NIBBLE> bitCalculators;

    float upsamplerGain, downsamplerGain;

#endif

	Btfld() {
		config(PARAMS_LEN, INPUTS_LEN, OUTPUTS_LEN, LIGHTS_LEN);
		configParam(GAIN_PARAM, 0.f, 2.f, 1.f, "Gain");
		configParam(CV_PARAM, 0.f, 1.f, 0.f, "Gain CV");
		configParam(RANGE_PARAM, 0.f, 1.f, 0.f, "Range (+10/±5)");
		configInput(INPUT_INPUT, "In");
		configInput(CV_INPUT, "CV");
		configInput(INJECT_INPUT, "Inject");
		configOutput(SAW_OUTPUT, "Saw");
		configOutput(BIT_OUTPUT + 3, "Out bit 8");
		configOutput(BIT_OUTPUT + 2, "Out bit 4");
		configOutput(BIT_OUTPUT + 1, "Out bit 2");
        configOutput(BIT_OUTPUT, "Out bit 1");
        configOutput(STEP_OUT_OUTPUT, "Step");

#if !defined(METAMODULE) && !defined(BTFLD_BASE_RATE)
        std::fill(workingBuffer.begin(), workingBuffer.end(), 0.f);

        float kernelSum = 0;
        for (auto i = 0; i < BTFLD_UPSAMPLE_RATE * BTFLD_UPSAMPLE_QUALITY; ++i) {
            kernelSum += cvUpsampler.kernel[i];
        }
        upsamplerGain = 1.f / kernelSum;
        kernelSum = 0;
        for (auto i = 0; i < BTFLD_UPSAMPLE_RATE * BTFLD_UPSAMPLE_QUALITY; ++i) {
            kernelSum += downsamplers[0].kernel[i];
        }
        downsamplerGain = 1.f / kernelSum;

        bitCalculators[0].shiftAmount = 0;
        bitCalculators[1].shiftAmount = 1;
        bitCalculators[2].shiftAmount = 2;
        bitCalculators[3].shiftAmount = 3;
#endif
    }

    void onSampleRateChange(const SampleRateChangeEvent& e) override {
        stepFilter.setDecay(0.25f * e.sampleRate);
        sawFilter.setDecay(0.25f * e.sampleRate);
#if defined(METAMODULE) || defined(BTFLD_BASE_RATE)
        sawLP.setCutoff(10000.f, e.sampleRate);
        stepLP.setCutoff(10000.f, e.sampleRate);
#else
        for (auto& b : bits) { b = 0; }
        for (auto& b : bitFilter) { b = 0; }
#endif
    }

    void setPosNegLight(int light, float voltage, float sampleTime) {
        lights[light + 0].setBrightnessSmooth(std::min(std::max(0.f, -voltage), 5.f) * 0.2f, sampleTime);
        lights[light + 2].setBrightnessSmooth(std::min(std::max(0.f, voltage), 5.f) * 0.2f, sampleTime);
    }

    void process(const ProcessArgs& args) override {
#if defined(METAMODULE) && defined(__arm__)
        { uint32_t fpscr; asm volatile("vmrs %0, fpscr" : "=r"(fpscr)); fpscr |= (1u << 24); asm volatile("vmsr fpscr, %0" : : "r"(fpscr)); }
#endif
        const bool updateLights = (++lightDivider >= LIGHT_DIVIDER);
        if (updateLights) lightDivider = 0;
        const float lightDeltaTime = args.sampleTime * LIGHT_DIVIDER;

#if defined(METAMODULE) || defined(BTFLD_BASE_RATE)

        // Gain
        auto cvInput = inputs[CV_INPUT].isConnected() ? inputs[CV_INPUT].getVoltage() : feedback;
        auto gain = params[GAIN_PARAM].getValue() + params[CV_PARAM].getValue() * cvInput * 0.1f;
        if (updateLights) setPosNegLight(CV_INDICATOR_LIGHT, params[CV_PARAM].getValue() * cvInput, lightDeltaTime);

        // Input
        auto inputSignal = inputs[INPUT_INPUT].isConnected() ? inputs[INPUT_INPUT].getVoltage() : 0.f;
        auto bipolar = params[RANGE_PARAM].getValue() > 0.5f;
        if (updateLights) setPosNegLight(INPUT_INDICATOR_LIGHT, inputSignal, lightDeltaTime);

        // Inject
        auto inject = inputs[INJECT_INPUT].isConnected() ? inputs[INJECT_INPUT].getVoltage() : 0.f;
        if (updateLights) setPosNegLight(INJECT_INDICATOR_LIGHT, inject, lightDeltaTime);

        // Saturated pre-quantizer signal v ∈ [0, 11.7]
        float v = inputSignal * gain + (bipolar ? 5.f : 0.f) + inject;
        v = std::min(std::max(0.f, v), 11.7f);

        // ADAA bandlimited sawtooth: average of frac(1.6·v) over [v_prev, v]
        float F = adaa_antideriv(v);
        float saw;
        float dv = v - v_prev;
        if (std::abs(dv) < 1e-6f) {
            float s = 1.6f * v;
            saw = s - floorf(s);
        } else {
            saw = (F - F_prev) / dv;
        }
        v_prev = v;
        F_prev = F;

        // Quantizer: integer step index and bit outputs
        float scaled = 1.6f * v;
        int step = static_cast<int>(scaled);
        if (step > 15) step = 15;

        for (int b = 0; b < NIBBLE; ++b) {
            float bit = ((step >> b) & 1) ? 1.f : 0.f;
            outputs[BIT_OUTPUT + b].setVoltage(bit * 10.f - (bipolar ? 5.f : 0.f));
            if (updateLights) lights[BIT_INDICATOR_LIGHT + b].setBrightnessSmooth(bit, lightDeltaTime);
        }

        // Step output
        float steps = static_cast<float>(step);
        float rescaledSteps = steps * (10.f / 16.f);
        auto filteredSteps = stepFilter.process(rescaledSteps);
        auto smoothedSteps = stepLP.process(bipolar ? filteredSteps : rescaledSteps);
        outputs[STEP_OUT_OUTPUT].setVoltage(smoothedSteps);

        if (updateLights) {
            for (int l = 0; l < 8; ++l) {
                auto brightness = 0.f;
                if (bipolar && l < 4) {
                    brightness += l * 2 > steps ? 0.5f : 0.f;
                    brightness += l * 2 + 1 > steps ? 0.5f : 0.f;
                } else {
                    brightness += l * 2 <= steps ? 0.5f : 0.f;
                    brightness += l * 2 + 1 <= steps ? 0.5f : 0.f;
                }
                lights[LEVEL_LIGHT + l].setBrightnessSmooth(brightness, lightDeltaTime);
            }
        }

        // SAW output: ADAA result ∈ [0,1), scaled to voltage, AC-coupled in bipolar, LP smoothed
        saw *= 10.f;
        auto filteredSaw = sawFilter.process(saw);
        auto smoothedSaw = sawLP.process(bipolar ? filteredSaw : saw);
        feedback = std::min(std::max(-12.f, smoothedSaw), 12.f);

        if (updateLights) setPosNegLight(SAW_INDICATOR_LIGHT, feedback, lightDeltaTime);
        outputs[SAW_OUTPUT].setVoltage(feedback);

#else // original oversampled path

        auto cvInput = inputs[CV_INPUT].isConnected() ? inputs[CV_INPUT].getVoltage() : feedback;
        auto gain = params[GAIN_PARAM].getValue() + params[CV_PARAM].getValue() * cvInput * 0.1f;

        cvUpsampler.process(gain * upsamplerGain, upsampledCV.data());

        if (updateLights) setPosNegLight(CV_INDICATOR_LIGHT, params[CV_PARAM].getValue() * cvInput, lightDeltaTime);

        auto inputSignal = inputs[INPUT_INPUT].isConnected() ? inputs[INPUT_INPUT].getVoltage() : 0.f;
        auto bipolar = params[RANGE_PARAM].getValue() > 0.5f;
        if (updateLights) setPosNegLight(INPUT_INDICATOR_LIGHT, inputSignal, lightDeltaTime);

        if (inputs[INPUT_INPUT].isConnected()) {
            inputUpsampler.process(inputSignal * upsamplerGain, upsampledInput.data());
        } else {
            upsampledInput.fill(0.f);
        }

        auto inject = inputs[INJECT_INPUT].getVoltage();
        if (updateLights) setPosNegLight(INJECT_INDICATOR_LIGHT, inject, lightDeltaTime);

        if (inputs[INJECT_INPUT].isConnected()) {
            injectUpsampler.process(inject * upsamplerGain, upsampledInject.data());
        } else {
            upsampledInject.fill(0.f);
        }

        for (auto ss = 0; ss < BTFLD_UPSAMPLE_RATE; ++ss) {
            upsampledInput[ss] *= upsampledCV[ss];
            upsampledInput[ss] += bipolar ? 5.f : 0.f;
            upsampledInput[ss] += upsampledInject[ss];

            upsampledInput[ss] = std::min(std::max(0.f, upsampledInput[ss]), 11.7f);
            upsampledInput[ss] *= (16.f / 10.f);

            upsampledStepOut[ss] = std::max(upsampledInput[ss] - 15.99f, 0.f);
            upsampledInput[ss] = std::min(upsampledInput[ss], 15.99f);

            upsampledStepOut[ss] += std::floor(upsampledInput[ss]);
            upsampledSaw[ss] = std::min(std::max(0.f, upsampledInput[ss] - upsampledStepOut[ss]), 1.1f);
        }

        for (auto b = 0; b < NIBBLE; ++b) {
            for (int ss = 0; ss < BTFLD_UPSAMPLE_RATE; ++ss) {
                workingBuffer[ss] = bitCalculators[b].process(upsampledInput[ss]);
            }
            bits[b] = downsamplers[b].process(workingBuffer.data()) * downsamplerGain;
        }

        for (auto i = 0; i < NIBBLE; ++i) {
            outputs[BIT_OUTPUT + i].setVoltage(bits[i] * 10.f - (bipolar ? 5.f : 0.f));
            if (updateLights) lights[BIT_INDICATOR_LIGHT + i].setBrightnessSmooth(bits[i], lightDeltaTime);
        }

        float steps = stepDownsampler.process(upsampledStepOut.data()) * downsamplerGain;
        float saw = sawDownsampler.process(upsampledSaw.data()) * downsamplerGain;

        if (updateLights) {
            for (int l = 0; l < 8; ++l) {
                auto brightness = 0.f;
                if (bipolar && l < 4) {
                    brightness += l * 2 > steps ? 0.5f : 0.f;
                    brightness += l * 2 + 1 > steps ? 0.5f : 0.f;
                } else {
                    brightness += l * 2 <= steps ? 0.5f : 0.f;
                    brightness += l * 2 + 1 <= steps ? 0.5f : 0.f;
                }
                lights[LEVEL_LIGHT + l].setBrightnessSmooth(brightness, lightDeltaTime);
            }
        }

        saw *= 10.f;
        auto rescaledSteps = steps * (10.f / 16.f);
        auto filteredSteps = stepFilter.process(rescaledSteps);
        outputs[STEP_OUT_OUTPUT].setVoltage(bipolar ? filteredSteps : rescaledSteps);
        auto filteredSaw = sawFilter.process(saw);
        feedback = std::min(std::max(-12.f, (bipolar ? filteredSaw : saw)), 12.f);

        previousInputSignal = inputSignal;
        previousSteps = steps;
        if (updateLights) setPosNegLight(SAW_INDICATOR_LIGHT, feedback, lightDeltaTime);
        outputs[SAW_OUTPUT].setVoltage(feedback);

#endif
    }
};


struct BtfldWidget : ModuleWidget {
	BtfldWidget(Btfld* module) {
		setModule(module);
		setPanel(createPanel(asset::plugin(pluginInstance, "res/btfld.svg"),
                             asset::plugin(pluginInstance, "res/btfld-dark.svg")));

		addChild(createWidget<ThemedScrew>(Vec(RACK_GRID_WIDTH, 0)));
		addChild(createWidget<ThemedScrew>(Vec(RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

		addParam(createParamCentered<SchlappiSilverKnob>(mm2px(Vec(15.22, 16.406)), module, Btfld::GAIN_PARAM));
		addParam(createParamCentered<SchlappiSilverKnob>(mm2px(Vec(15.22, 41.785)), module, Btfld::CV_PARAM));
		addParam(createParamCentered<SchlappiToggleVertical2pos>(mm2px(Vec(7.217, 58.613)), module, Btfld::RANGE_PARAM));

		addInput(createInputCentered<ThemedPJ301MPort>(mm2px(Vec(7.196, 72.886)), module, Btfld::INPUT_INPUT));
		addInput(createInputCentered<ThemedPJ301MPort>(mm2px(Vec(7.196, 85.892)), module, Btfld::CV_INPUT));
		addInput(createInputCentered<ThemedPJ301MPort>(mm2px(Vec(7.196, 98.729)), module, Btfld::INJECT_INPUT));

		addOutput(createOutputCentered<ThemedPJ301MPort>(mm2px(Vec(20.541, 60.048)), module, Btfld::SAW_OUTPUT));
		addOutput(createOutputCentered<ThemedPJ301MPort>(mm2px(Vec(20.541, 72.886)), module, Btfld::BIT_OUTPUT + 3));
		addOutput(createOutputCentered<ThemedPJ301MPort>(mm2px(Vec(20.541, 85.892)), module, Btfld::BIT_OUTPUT + 2));
		addOutput(createOutputCentered<ThemedPJ301MPort>(mm2px(Vec(20.539, 98.809)), module, Btfld::BIT_OUTPUT + 1));
        addOutput(createOutputCentered<ThemedPJ301MPort>(mm2px(Vec(20.541, 111.736)), module, Btfld::BIT_OUTPUT + 0));
        addOutput(createOutputCentered<ThemedPJ301MPort>(mm2px(Vec(7.196, 111.736)), module, Btfld::STEP_OUT_OUTPUT));

		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 11.655)), module, Btfld::LEVEL_LIGHT + 7));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 16.659)), module, Btfld::LEVEL_LIGHT + 6));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 21.663)), module, Btfld::LEVEL_LIGHT + 5));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 26.646)), module, Btfld::LEVEL_LIGHT + 4));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 31.629)), module, Btfld::LEVEL_LIGHT + 3));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 36.654)), module, Btfld::LEVEL_LIGHT + 2));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 41.637)), module, Btfld::LEVEL_LIGHT + 1));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(3.247, 46.62)), module, Btfld::LEVEL_LIGHT + 0));
		addChild(createLightCentered<MediumLight<RedGreenBlueLight>>(mm2px(Vec(27.213, 53.376)), module, Btfld::SAW_INDICATOR_LIGHT));
		addChild(createLightCentered<MediumLight<RedGreenBlueLight>>(mm2px(Vec(13.868, 66.552)), module, Btfld::INPUT_INDICATOR_LIGHT));
		addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(27.213, 66.552)), module, Btfld::BIT_INDICATOR_LIGHT + 3));
        addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(27.213, 79.389)), module, Btfld::BIT_INDICATOR_LIGHT + 2));
        addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(27.213, 92.543)), module, Btfld::BIT_INDICATOR_LIGHT + 1));
        addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(27.213, 105.232)), module, Btfld::BIT_INDICATOR_LIGHT + 0));
        addChild(createLightCentered<MediumLight<RedGreenBlueLight>>(mm2px(Vec(13.868, 79.389)), module, Btfld::CV_INDICATOR_LIGHT));
        addChild(createLightCentered<MediumLight<RedGreenBlueLight>>(mm2px(Vec(13.868, 92.543)), module, Btfld::INJECT_INDICATOR_LIGHT));
        addChild(createLightCentered<MediumLight<BlueLight>>(mm2px(Vec(13.868, 105.232)), module, Btfld::STEP_INDICATOR_LIGHT));
	}
};


Model* modelBtfld = createModel<Btfld, BtfldWidget>("BTFLD");
