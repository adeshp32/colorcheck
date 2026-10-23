// node_modules/typed-cstruct/dist/builders/struct.js
var Struct = class _Struct {
  fields;
  #size;
  constructor(fields) {
    this.fields = fields;
    this.#size = this.fields.reduce((acc, f) => acc + f.builder.size, 0);
  }
  get size() {
    return this.#size;
  }
  field(name, builder) {
    return new _Struct([...this.fields, { name, builder, offset: this.#size }]);
  }
  override(name, builder) {
    const fields = this.fields.reduce((acc, f) => {
      const prev = acc.at(-1);
      const offset = prev ? prev.offset + prev.builder.size : 0;
      acc.push(f.name === name ? { name, builder, offset } : { ...f, offset });
      return acc;
    }, []);
    return new _Struct(fields);
  }
  #proxy(opts, useProxy = false) {
    const { buf, offset = 0, endian = "little" } = opts;
    const self = this;
    const base = Object.fromEntries(self.fields.map((f) => [f.name, true]));
    const ret = new Proxy(base, {
      get(_, prop) {
        if (typeof prop !== "string")
          return void 0;
        const field = self.fields.find((f) => f.name === prop);
        if (!field)
          return void 0;
        if (useProxy && typeof field.builder.proxy === "function") {
          return field.builder.proxy({ buf, offset: offset + field.offset, endian }, ret);
        }
        return field.builder.read({ buf, offset: offset + field.offset, endian }, ret);
      },
      set(_, prop, value) {
        if (typeof prop !== "string")
          return false;
        const field = self.fields.find((f) => f.name === prop);
        if (!field)
          return false;
        if (typeof field.builder.write !== "function")
          return false;
        field.builder.write(value, { buf, offset: offset + field.offset, endian }, ret);
        return true;
      }
    });
    return ret;
  }
  proxy(opts) {
    return this.#proxy(opts, true);
  }
  read(opts) {
    const proxy = this.#proxy(opts);
    const ret = Object.fromEntries(Object.entries(proxy));
    return ret;
  }
  write(value, opts) {
    const proxy = this.#proxy(opts);
    for (const key of this.fields.map((f) => f.name)) {
      proxy[key] = value[key];
    }
  }
};

// node_modules/typed-cstruct/dist/utils.js
var big = "big";
function view(buf) {
  return new DataView(buf.buffer);
}
function readU8(opts) {
  return view(opts.buf).getUint8(opts.offset || 0);
}
function writeU8(value, opts) {
  view(opts.buf).setUint8(opts.offset || 0, value);
}
function readI8(opts) {
  return view(opts.buf).getInt8(opts.offset || 0);
}
function writeI8(value, opts) {
  view(opts.buf).setInt8(opts.offset || 0, value);
}
function readU16(opts) {
  return view(opts.buf).getUint16(opts.offset || 0, opts.endian !== big);
}
function writeU16(value, opts) {
  view(opts.buf).setUint16(opts.offset || 0, value, opts.endian !== big);
}
function readI16(opts) {
  return view(opts.buf).getInt16(opts.offset || 0, opts.endian !== big);
}
function writeI16(value, opts) {
  view(opts.buf).setInt16(opts.offset || 0, value, opts.endian !== big);
}
function readU32(opts) {
  return view(opts.buf).getUint32(opts.offset || 0, opts.endian !== big);
}
function writeU32(value, opts) {
  view(opts.buf).setUint32(opts.offset || 0, value, opts.endian !== big);
}
function readI32(opts) {
  return view(opts.buf).getInt32(opts.offset || 0, opts.endian !== big);
}
function writeI32(value, opts) {
  view(opts.buf).setInt32(opts.offset || 0, value, opts.endian !== big);
}
function readU64(opts) {
  return view(opts.buf).getBigUint64(opts.offset || 0, opts.endian !== big);
}
function writeU64(value, opts) {
  view(opts.buf).setBigUint64(opts.offset || 0, value, opts.endian !== big);
}
function readI64(opts) {
  return view(opts.buf).getBigInt64(opts.offset || 0, opts.endian !== big);
}
function writeI64(value, opts) {
  view(opts.buf).setBigInt64(opts.offset || 0, value, opts.endian !== big);
}
function readF32(opts) {
  return view(opts.buf).getFloat32(opts.offset || 0, opts.endian !== big);
}
function writeF32(value, opts) {
  view(opts.buf).setFloat32(opts.offset || 0, value, opts.endian !== big);
}
function readF64(opts) {
  return view(opts.buf).getFloat64(opts.offset || 0, opts.endian !== big);
}
function writeF64(value, opts) {
  view(opts.buf).setFloat64(opts.offset || 0, value, opts.endian !== big);
}

// node_modules/typed-cstruct/dist/builders/array.js
function sizedArray(builder, size) {
  const proxy = (opts, _, useProxy = true) => {
    return new Proxy(Array.from({ length: size }), {
      get(target, prop) {
        const defaultValue = Reflect.get(target, prop);
        if (defaultValue !== void 0 || typeof prop === "symbol")
          return defaultValue;
        const index = Number(prop);
        if (index < 0 || size <= index)
          return void 0;
        const { offset = 0 } = opts;
        if (useProxy && typeof builder.proxy === "function") {
          return builder.proxy({ ...opts, offset: offset + index * builder.size }, {});
        }
        return builder.read({ ...opts, offset: offset + index * builder.size }, {});
      },
      set(_2, prop, value) {
        if (typeof prop === "symbol")
          return false;
        const index = Number(prop);
        if (!Number.isFinite(index))
          return false;
        const { offset = 0 } = opts;
        if (typeof builder.write !== "function")
          return false;
        builder.write?.(value, { ...opts, offset: offset + index * builder.size }, {});
        return true;
      }
    });
  };
  return {
    size: size * builder.size,
    proxy,
    read(opts, ctx) {
      return proxy(opts, ctx, false).slice();
    },
    write(value, opts, ctx) {
      if (typeof builder.write !== "function")
        return;
      const { offset = 0 } = opts;
      for (let i = 0; i < size; i++) {
        builder.write(value[i], { ...opts, offset: offset + i * builder.size }, ctx);
      }
    }
  };
}
function pointerArrayFromLengthField(builder, fieldName) {
  return {
    size: 4,
    read(opts, ctx) {
      const ptr2 = readU32(opts);
      const size = ctx[fieldName];
      return Array.from({ length: size }, (_, i) => builder.read({ ...opts, offset: ptr2 + i * builder.size }, {}));
    }
  };
}

// node_modules/typed-cstruct/dist/builders/num.js
var u8 = {
  size: 1,
  read: readU8,
  write: writeU8
};
var i8 = {
  size: 1,
  read: readI8,
  write: writeI8
};
var u16 = {
  size: 2,
  read: readU16,
  write: writeU16
};
var i16 = {
  size: 2,
  read: readI16,
  write: writeI16
};
var u32 = {
  size: 4,
  read: readU32,
  write: writeU32
};
var i32 = {
  size: 4,
  read: readI32,
  write: writeI32
};
var u64 = {
  size: 8,
  read: readU64,
  write: writeU64
};
var i64 = {
  size: 8,
  read: readI64,
  write: writeI64
};
var f32 = {
  size: 4,
  read: readF32,
  write: writeF32
};
var f64 = {
  size: 8,
  read: readF64,
  write: writeF64
};
function enumLike(realType, variants) {
  return {
    size: realType.size,
    read(opts, ctx) {
      const value = realType.read(opts, ctx);
      const variant = Object.entries(variants).find(([_, v]) => v === value)?.[0];
      if (variant === void 0) {
        throw new Error(`Unknown enum value: ${value}`);
      }
      return variant;
    },
    write(value, opts, ctx) {
      const variant = variants[value];
      if (variant === void 0) {
        throw new Error(`Unknown enum variant: ${String(value)}`);
      }
      return realType.write?.(variant, opts, ctx);
    }
  };
}

// node_modules/typed-cstruct/dist/builders/string.js
var defaultDecode = (buf) => new TextDecoder().decode(buf);
var defaultEncode = (val) => new TextEncoder().encode(val);
function charPointerAsString(decode) {
  return {
    size: 4,
    read(opts) {
      const ptr2 = readU32(opts);
      const zeorIndex = opts.buf.indexOf(0, ptr2);
      return (decode ?? defaultDecode)(opts.buf.slice(ptr2, zeorIndex));
    }
  };
}
function sizedCharArrayAsString(size, options = {}) {
  const { nullTermination = true, decode = defaultDecode, encode = defaultEncode } = options;
  return {
    size,
    read(opts) {
      const { buf, offset = 0 } = opts;
      const end = nullTermination ? buf.indexOf(0, offset) : offset + size;
      return (decode ?? defaultDecode)(buf.slice(offset, end));
    },
    write(value, opts) {
      const { buf, offset = 0 } = opts;
      const encoded = (encode ?? defaultEncode)(value);
      for (let i = 0; i < size; i++) {
        buf[offset + i] = i < encoded.length ? encoded[i] : 0;
      }
    }
  };
}

// node_modules/typed-cstruct/dist/builders/utils.js
function ptr(builder) {
  const read = (opts) => {
    const p = readU32(opts);
    if (p === 0)
      return null;
    return builder.read({ ...opts, offset: p }, {});
  };
  const write = builder.write ? (value, opts) => {
    if (value === null)
      throw new Error("Cannot write null pointer");
    const p = readU32(opts);
    if (p === 0)
      throw new Error("Cannot write to null pointer");
    builder.write?.(value, { ...opts, offset: p }, {});
  } : void 0;
  const proxy = builder.proxy ? (opts) => {
    const p = readU32(opts);
    if (p === 0)
      return null;
    return builder.proxy?.({ ...opts, offset: p }, {}) ?? null;
  } : void 0;
  return { size: 4, read, write, proxy };
}

// node_modules/typed-cstruct/dist/index.js
var Struct2 = class extends Struct {
  constructor() {
    super([]);
  }
};

// node_modules/@colorhythm/libraw-wasm/dist/libraw-types.js
function LibRaw_image_formats() {
  return enumLike(u32, {
    LIBRAW_IMAGE_BITMAP: 2,
    LIBRAW_IMAGE_H265: 4,
    LIBRAW_IMAGE_JPEG: 1,
    LIBRAW_IMAGE_JPEGXL: 3
  });
}
function LibRaw_thumbnail_formats() {
  return enumLike(u32, {
    LIBRAW_THUMBNAIL_BITMAP: 2,
    LIBRAW_THUMBNAIL_BITMAP16: 3,
    LIBRAW_THUMBNAIL_H265: 6,
    LIBRAW_THUMBNAIL_JPEG: 1,
    LIBRAW_THUMBNAIL_JPEGXL: 7,
    LIBRAW_THUMBNAIL_LAYER: 4,
    LIBRAW_THUMBNAIL_ROLLEI: 5,
    LIBRAW_THUMBNAIL_UNKNOWN: 0
  });
}
function UINT64() {
  return u64;
}
function libraw_afinfo_item_t() {
  return new Struct2().field("AFInfoData_tag", u32).field("AFInfoData_order", i16).field("AFInfoData_version", u32).field("AFInfoData_length", u32).field("AFInfoData", ptr(uchar()));
}
function libraw_area_t() {
  return new Struct2().field("t", i16).field("l", i16).field("b", i16).field("r", i16);
}
function libraw_canon_makernotes_t() {
  return new Struct2().field("ColorDataVer", i32).field("ColorDataSubVer", i32).field("SpecularWhiteLevel", i32).field("NormalWhiteLevel", i32).field("ChannelBlackLevel", sizedArray(i32, 4)).field("AverageBlackLevel", i32).field("multishot", sizedArray(u32, 4)).field("MeteringMode", i16).field("SpotMeteringMode", i16).field("FlashMeteringMode", uchar()).field("FlashExposureLock", i16).field("ExposureMode", i16).field("AESetting", i16).field("ImageStabilization", i16).field("FlashMode", i16).field("FlashActivity", i16).field("FlashBits", i16).field("ManualFlashOutput", i16).field("FlashOutput", i16).field("FlashGuideNumber", i16).field("ContinuousDrive", i16).field("SensorWidth", i16).field("SensorHeight", i16).field("AFMicroAdjMode", i32).field("AFMicroAdjValue", f32).field("MakernotesFlip", i16).field("AutoRotateMode", i16).field("RecordMode", i16).field("SRAWQuality", i16).field("wbi", u32).field("RF_lensID", i16).field("AutoLightingOptimizer", i32).field("HighlightTonePriority", i32).field("Quality", i16).field("CanonLog", i32).field("DefaultCropAbsolute", libraw_area_t()).field("RecommendedImageArea", libraw_area_t()).field("LeftOpticalBlack", libraw_area_t()).field("UpperOpticalBlack", libraw_area_t()).field("ActiveArea", libraw_area_t()).field("ISOgain", sizedArray(i16, 2));
}
function libraw_dnglens_t() {
  return new Struct2().field("MinFocal", f32).field("MaxFocal", f32).field("MaxAp4MinFocal", f32).field("MaxAp4MaxFocal", f32);
}
function libraw_fuji_info_t() {
  return new Struct2().field("ExpoMidPointShift", f32).field("DynamicRange", ushort()).field("FilmMode", ushort()).field("DynamicRangeSetting", ushort()).field("DevelopmentDynamicRange", ushort()).field("AutoDynamicRange", ushort()).field("DRangePriority", ushort()).field("DRangePriorityAuto", ushort()).field("DRangePriorityFixed", ushort()).field("FujiModel", sizedArray(u8, 33)).field("FujiModel2", sizedArray(u8, 33)).field("BrightnessCompensation", f32).field("FocusMode", ushort()).field("AFMode", ushort()).field("FocusPixel", sizedArray(ushort(), 2)).field("PrioritySettings", ushort()).field("FocusSettings", u32).field("AF_C_Settings", u32).field("FocusWarning", ushort()).field("ImageStabilization", sizedArray(ushort(), 3)).field("FlashMode", ushort()).field("WB_Preset", ushort()).field("ShutterType", ushort()).field("ExrMode", ushort()).field("Macro", ushort()).field("Rating", u32).field("CropMode", ushort()).field("SerialSignature", sizedArray(u8, 13)).field("SensorID", sizedArray(u8, 5)).field("RAFVersion", sizedArray(u8, 5)).field("RAFDataGeneration", i32).field("RAFDataVersion", ushort()).field("isTSNERDTS", i32).field("DriveMode", i16).field("BlackLevel", sizedArray(ushort(), 9)).field("RAFData_ImageSizeTable", sizedArray(u32, 32)).field("AutoBracketing", i32).field("SequenceNumber", i32).field("SeriesLength", i32).field("PixelShiftOffset", sizedArray(f32, 2)).field("ImageCount", i32);
}
function libraw_gps_info_t() {
  return new Struct2().field("latitude", sizedArray(f32, 3)).field("longitude", sizedArray(f32, 3)).field("gpstimestamp", sizedArray(f32, 3)).field("altitude", f32).field("altref", u8).field("latref", u8).field("longref", u8).field("gpsstatus", u8).field("gpsparsed", u8);
}
function libraw_hasselblad_makernotes_t() {
  return new Struct2().field("BaseISO", i32).field("Gain", f64).field("Sensor", sizedArray(u8, 8)).field("SensorUnit", sizedArray(u8, 64)).field("HostBody", sizedArray(u8, 64)).field("SensorCode", i32).field("SensorSubCode", i32).field("CoatingCode", i32).field("uncropped", i32).field("CaptureSequenceInitiator", sizedArray(u8, 32)).field("SensorUnitConnector", sizedArray(u8, 64)).field("format", i32).field("nIFD_CM", sizedArray(i32, 2)).field("RecommendedCrop", sizedArray(i32, 2)).field("mnColorMatrix", sizedArray(sizedArray(f64, 3), 4));
}
function libraw_imgother_t() {
  return new Struct2().field("iso_speed", f32).field("shutter", f32).field("aperture", f32).field("focal_len", f32).field("timestamp", time_t()).field("shot_order", u32).field("gpsdata", sizedArray(u32, 32)).field("parsed_gps", libraw_gps_info_t()).field("desc", sizedArray(u8, 512)).field("artist", sizedArray(u8, 64)).field("analogbalance", sizedArray(f32, 4));
}
function libraw_iparams_t() {
  return new Struct2().field("guard", sizedArray(u8, 4)).field("make", sizedArray(u8, 64)).field("model", sizedArray(u8, 64)).field("software", sizedArray(u8, 64)).field("normalized_make", sizedArray(u8, 64)).field("normalized_model", sizedArray(u8, 64)).field("maker_index", u32).field("raw_count", u32).field("dng_version", u32).field("is_foveon", u32).field("colors", i32).field("filters", u32).field("xtrans", sizedArray(sizedArray(u8, 6), 6)).field("xtrans_abs", sizedArray(sizedArray(u8, 6), 6)).field("cdesc", sizedArray(u8, 5)).field("xmplen", u32).field("xmpdata", ptr(u8));
}
function libraw_kodak_makernotes_t() {
  return new Struct2().field("BlackLevelTop", ushort()).field("BlackLevelBottom", ushort()).field("offset_left", i16).field("offset_top", i16).field("clipBlack", ushort()).field("clipWhite", ushort()).field("romm_camDaylight", sizedArray(sizedArray(f32, 3), 3)).field("romm_camTungsten", sizedArray(sizedArray(f32, 3), 3)).field("romm_camFluorescent", sizedArray(sizedArray(f32, 3), 3)).field("romm_camFlash", sizedArray(sizedArray(f32, 3), 3)).field("romm_camCustom", sizedArray(sizedArray(f32, 3), 3)).field("romm_camAuto", sizedArray(sizedArray(f32, 3), 3)).field("val018percent", ushort()).field("val100percent", ushort()).field("val170percent", ushort()).field("MakerNoteKodak8a", i16).field("ISOCalibrationGain", f32).field("AnalogISO", f32);
}
function libraw_lensinfo_t() {
  return new Struct2().field("MinFocal", f32).field("MaxFocal", f32).field("MaxAp4MinFocal", f32).field("MaxAp4MaxFocal", f32).field("EXIF_MaxAp", f32).field("LensMake", sizedArray(u8, 128)).field("Lens", sizedArray(u8, 128)).field("LensSerial", sizedArray(u8, 128)).field("InternalLensSerial", sizedArray(u8, 128)).field("FocalLengthIn35mmFormat", ushort()).field("nikon", libraw_nikonlens_t()).field("dng", libraw_dnglens_t()).field("makernotes", libraw_makernotes_lens_t());
}
function libraw_makernotes_lens_t() {
  return new Struct2().field("LensID", UINT64()).field("Lens", sizedArray(u8, 128)).field("LensFormat", ushort()).field("LensMount", ushort()).field("CamID", UINT64()).field("CameraFormat", ushort()).field("CameraMount", ushort()).field("body", sizedArray(u8, 64)).field("FocalType", i16).field("LensFeatures_pre", sizedArray(u8, 16)).field("LensFeatures_suf", sizedArray(u8, 16)).field("MinFocal", f32).field("MaxFocal", f32).field("MaxAp4MinFocal", f32).field("MaxAp4MaxFocal", f32).field("MinAp4MinFocal", f32).field("MinAp4MaxFocal", f32).field("MaxAp", f32).field("MinAp", f32).field("CurFocal", f32).field("CurAp", f32).field("MaxAp4CurFocal", f32).field("MinAp4CurFocal", f32).field("MinFocusDistance", f32).field("FocusRangeIndex", f32).field("LensFStops", f32).field("TeleconverterID", UINT64()).field("Teleconverter", sizedArray(u8, 128)).field("AdapterID", UINT64()).field("Adapter", sizedArray(u8, 128)).field("AttachmentID", UINT64()).field("Attachment", sizedArray(u8, 128)).field("FocalUnits", ushort()).field("FocalLengthIn35mmFormat", f32);
}
function libraw_makernotes_t() {
  return new Struct2().field("canon", libraw_canon_makernotes_t()).field("nikon", libraw_nikon_makernotes_t()).field("hasselblad", libraw_hasselblad_makernotes_t()).field("fuji", libraw_fuji_info_t()).field("olympus", libraw_olympus_makernotes_t()).field("sony", libraw_sony_info_t()).field("kodak", libraw_kodak_makernotes_t()).field("panasonic", libraw_panasonic_makernotes_t()).field("pentax", libraw_pentax_makernotes_t()).field("phaseone", libraw_p1_makernotes_t()).field("ricoh", libraw_ricoh_makernotes_t()).field("samsung", libraw_samsung_makernotes_t()).field("common", libraw_metadata_common_t());
}
function libraw_metadata_common_t() {
  return new Struct2().field("FlashEC", f32).field("FlashGN", f32).field("CameraTemperature", f32).field("SensorTemperature", f32).field("SensorTemperature2", f32).field("LensTemperature", f32).field("AmbientTemperature", f32).field("BatteryTemperature", f32).field("exifAmbientTemperature", f32).field("exifHumidity", f32).field("exifPressure", f32).field("exifWaterDepth", f32).field("exifAcceleration", f32).field("exifCameraElevationAngle", f32).field("real_ISO", f32).field("exifExposureIndex", f32).field("ColorSpace", ushort()).field("firmware", sizedArray(u8, 128)).field("ExposureCalibrationShift", f32).field("afdata", sizedArray(libraw_afinfo_item_t(), 4)).field("afcount", i32);
}
function libraw_nikon_makernotes_t() {
  return new Struct2().field("ExposureBracketValue", f64).field("ActiveDLighting", ushort()).field("ShootingMode", ushort()).field("ImageStabilization", sizedArray(uchar(), 7)).field("VibrationReduction", uchar()).field("VRMode", uchar()).field("FlashSetting", sizedArray(u8, 13)).field("FlashType", sizedArray(u8, 20)).field("FlashExposureCompensation", sizedArray(uchar(), 4)).field("ExternalFlashExposureComp", sizedArray(uchar(), 4)).field("FlashExposureBracketValue", sizedArray(uchar(), 4)).field("FlashMode", uchar()).field("FlashExposureCompensation2", i8).field("FlashExposureCompensation3", i8).field("FlashExposureCompensation4", i8).field("FlashSource", uchar()).field("FlashFirmware", sizedArray(uchar(), 2)).field("ExternalFlashFlags", uchar()).field("FlashControlCommanderMode", uchar()).field("FlashOutputAndCompensation", uchar()).field("FlashFocalLength", uchar()).field("FlashGNDistance", uchar()).field("FlashGroupControlMode", sizedArray(uchar(), 4)).field("FlashGroupOutputAndCompensation", sizedArray(uchar(), 4)).field("FlashColorFilter", uchar()).field("NEFCompression", ushort()).field("ExposureMode", i32).field("ExposureProgram", i32).field("nMEshots", i32).field("MEgainOn", i32).field("ME_WB", sizedArray(f64, 4)).field("AFFineTune", uchar()).field("AFFineTuneIndex", uchar()).field("AFFineTuneAdj", i8).field("LensDataVersion", u32).field("FlashInfoVersion", u32).field("ColorBalanceVersion", u32).field("key", uchar()).field("NEFBitDepth", sizedArray(ushort(), 4)).field("HighSpeedCropFormat", ushort()).field("SensorHighSpeedCrop", libraw_sensor_highspeed_crop_t()).field("SensorWidth", ushort()).field("SensorHeight", ushort()).field("Active_D_Lighting", ushort()).field("PictureControlVersion", u32).field("PictureControlName", sizedArray(u8, 20)).field("PictureControlBase", sizedArray(u8, 20)).field("ShotInfoVersion", u32).field("ShotInfoFirmware", sizedArray(u8, 9)).field("BurstTable_0x0056_len", u32).field("BurstTable_0x0056", ptr(uchar())).field("BurstTable_0x0056_ver", ushort()).field("BurstTable_0x0056_gid", ushort()).field("BurstTable_0x0056_fnum", uchar()).field("MakernotesFlip", i16).field("RollAngle", f64).field("PitchAngle", f64).field("YawAngle", f64);
}
function libraw_nikonlens_t() {
  return new Struct2().field("EffectiveMaxAp", f32).field("LensIDNumber", uchar()).field("LensFStops", uchar()).field("MCUVersion", uchar()).field("LensType", uchar());
}
function libraw_olympus_makernotes_t() {
  return new Struct2().field("CameraType2", sizedArray(u8, 6)).field("ValidBits", ushort()).field("tagX640", u32).field("tagX641", u32).field("tagX642", u32).field("tagX643", u32).field("tagX644", u32).field("tagX645", u32).field("tagX646", u32).field("tagX647", u32).field("tagX648", u32).field("tagX649", u32).field("tagX650", u32).field("tagX651", u32).field("tagX652", u32).field("tagX653", u32).field("SensorCalibration", sizedArray(i32, 2)).field("DriveMode", sizedArray(ushort(), 5)).field("ColorSpace", ushort()).field("FocusMode", sizedArray(ushort(), 2)).field("AutoFocus", ushort()).field("AFPoint", ushort()).field("AFAreas", sizedArray(u32, 64)).field("AFPointSelected", sizedArray(f64, 5)).field("AFResult", ushort()).field("AFFineTune", uchar()).field("AFFineTuneAdj", sizedArray(i16, 3)).field("SpecialMode", sizedArray(u32, 3)).field("ZoomStepCount", ushort()).field("FocusStepCount", ushort()).field("FocusStepInfinity", ushort()).field("FocusStepNear", ushort()).field("FocusDistance", f64).field("AspectFrame", sizedArray(ushort(), 4)).field("StackedImage", sizedArray(u32, 2)).field("isLiveND", uchar()).field("LiveNDfactor", u32).field("Panorama_mode", ushort()).field("Panorama_frameNum", ushort());
}
function libraw_p1_makernotes_t() {
  return new Struct2().field("Software", sizedArray(u8, 64)).field("SystemType", sizedArray(u8, 64)).field("FirmwareString", sizedArray(u8, 256)).field("SystemModel", sizedArray(u8, 64));
}
function libraw_panasonic_makernotes_t() {
  return new Struct2().field("Compression", ushort()).field("BlackLevelDim", ushort()).field("BlackLevel", sizedArray(f32, 8)).field("Multishot", u32).field("gamma", f32).field("HighISOMultiplier", sizedArray(i32, 3)).field("FocusStepNear", i16).field("FocusStepCount", i16).field("ZoomPosition", u32).field("LensManufacturer", u32);
}
function libraw_pentax_makernotes_t() {
  return new Struct2().field("DriveMode", sizedArray(uchar(), 4)).field("FocusMode", sizedArray(ushort(), 2)).field("AFPointSelected", sizedArray(ushort(), 2)).field("AFPointSelected_Area", ushort()).field("AFPointsInFocus_version", i32).field("AFPointsInFocus", u32).field("FocusPosition", ushort()).field("DynamicRangeExpansion", sizedArray(uchar(), 4)).field("AFAdjustment", i16).field("AFPointMode", uchar()).field("MultiExposure", uchar()).field("Quality", ushort());
}
function libraw_processed_image_t() {
  return new Struct2().field("type_", LibRaw_image_formats()).field("height", ushort()).field("width", ushort()).field("colors", ushort()).field("bits", ushort()).field("data_size", u32).field("data", sizedArray(u8, 1));
}
function libraw_ricoh_makernotes_t() {
  return new Struct2().field("AFStatus", ushort()).field("AFAreaXPosition", sizedArray(u32, 2)).field("AFAreaYPosition", sizedArray(u32, 2)).field("AFAreaMode", ushort()).field("SensorWidth", u32).field("SensorHeight", u32).field("CroppedImageWidth", u32).field("CroppedImageHeight", u32).field("WideAdapter", ushort()).field("CropMode", ushort()).field("NDFilter", ushort()).field("AutoBracketing", ushort()).field("MacroMode", ushort()).field("FlashMode", ushort()).field("FlashExposureComp", f64).field("ManualFlashOutput", f64);
}
function libraw_samsung_makernotes_t() {
  return new Struct2().field("ImageSizeFull", sizedArray(u32, 4)).field("ImageSizeCrop", sizedArray(u32, 4)).field("ColorSpace", sizedArray(i32, 2)).field("key", sizedArray(u32, 11)).field("DigitalGain", f64).field("DeviceType", i32).field("LensFirmware", sizedArray(u8, 32));
}
function libraw_sensor_highspeed_crop_t() {
  return new Struct2().field("cleft", ushort()).field("ctop", ushort()).field("cwidth", ushort()).field("cheight", ushort());
}
function libraw_shootinginfo_t() {
  return new Struct2().field("DriveMode", i16).field("FocusMode", i16).field("MeteringMode", i16).field("AFPoint", i16).field("ExposureMode", i16).field("ExposureProgram", i16).field("ImageStabilization", i16).field("BodySerial", sizedArray(u8, 64)).field("InternalBodySerial", sizedArray(u8, 64));
}
function libraw_sony_info_t() {
  return new Struct2().field("CameraType", ushort()).field("Sony0x9400_version", uchar()).field("Sony0x9400_ReleaseMode2", uchar()).field("Sony0x9400_SequenceImageNumber", u32).field("Sony0x9400_SequenceLength1", uchar()).field("Sony0x9400_SequenceFileNumber", u32).field("Sony0x9400_SequenceLength2", uchar()).field("AFAreaModeSetting", u8).field("AFAreaMode", u16).field("FlexibleSpotPosition", sizedArray(ushort(), 2)).field("AFPointSelected", u8).field("AFPointSelected_0x201e", u8).field("nAFPointsUsed", i16).field("AFPointsUsed", sizedArray(u8, 10)).field("AFTracking", u8).field("AFType", u8).field("FocusLocation", sizedArray(ushort(), 4)).field("FocusPosition", ushort()).field("AFMicroAdjValue", i8).field("AFMicroAdjOn", i8).field("AFMicroAdjRegisteredLenses", uchar()).field("VariableLowPassFilter", ushort()).field("LongExposureNoiseReduction", u32).field("HighISONoiseReduction", ushort()).field("HDR", sizedArray(ushort(), 2)).field("group2010", ushort()).field("group9050", ushort()).field("len_group9050", ushort()).field("real_iso_offset", ushort()).field("MeteringMode_offset", ushort()).field("ExposureProgram_offset", ushort()).field("ReleaseMode2_offset", ushort()).field("MinoltaCamID", u32).field("firmware", f32).field("ImageCount3_offset", ushort()).field("ImageCount3", u32).field("ElectronicFrontCurtainShutter", u32).field("MeteringMode2", ushort()).field("SonyDateTime", sizedArray(u8, 20)).field("ShotNumberSincePowerUp", u32).field("PixelShiftGroupPrefix", ushort()).field("PixelShiftGroupID", u32).field("nShotsInPixelShiftGroup", u8).field("numInPixelShiftGroup", u8).field("prd_ImageHeight", ushort()).field("prd_ImageWidth", ushort()).field("prd_Total_bps", ushort()).field("prd_Active_bps", ushort()).field("prd_StorageMethod", ushort()).field("prd_BayerPattern", ushort()).field("SonyRawFileType", ushort()).field("RAWFileType", ushort()).field("RawSizeType", ushort()).field("Quality", u32).field("FileFormat", ushort()).field("MetaVersion", sizedArray(u8, 16)).field("AspectRatio", f32);
}
function libraw_thumbnail_t() {
  return new Struct2().field("tformat", LibRaw_thumbnail_formats()).field("twidth", ushort()).field("theight", ushort()).field("tlength", u32).field("tcolors", i32).field("thumb", ptr(u8));
}
function time_t() {
  return i64;
}
function uchar() {
  return u8;
}
function ushort() {
  return u16;
}

// node_modules/@colorhythm/libraw-wasm/dist/libraw.mjs
var Module = /* @__PURE__ */ (() => {
  return (async function(moduleArg = {}) {
    var moduleRtn;
    var Module2 = moduleArg;
    var readyPromiseResolve, readyPromiseReject;
    var readyPromise = new Promise((resolve, reject) => {
      readyPromiseResolve = resolve;
      readyPromiseReject = reject;
    });
    var ENVIRONMENT_IS_WEB = typeof window == "object";
    var ENVIRONMENT_IS_WORKER = typeof WorkerGlobalScope != "undefined";
    var ENVIRONMENT_IS_NODE = typeof process == "object" && typeof process.versions == "object" && typeof process.versions.node == "string" && process.type != "renderer";
    if (ENVIRONMENT_IS_NODE) {
      const { createRequire } = await import("module");
      var require2 = createRequire(import.meta.url);
    }
    var arguments_ = [];
    var thisProgram = "./this.program";
    var quit_ = (status, toThrow) => {
      throw toThrow;
    };
    var _scriptName = import.meta.url;
    var scriptDirectory = "";
    function locateFile(path) {
      if (Module2["locateFile"]) {
        return Module2["locateFile"](path, scriptDirectory);
      }
      return scriptDirectory + path;
    }
    var readAsync, readBinary;
    if (ENVIRONMENT_IS_NODE) {
      var fs = require2("fs");
      var nodePath = require2("path");
      if (_scriptName.startsWith("file:")) {
        scriptDirectory = nodePath.dirname(require2("url").fileURLToPath(_scriptName)) + "/";
      }
      readBinary = (filename) => {
        filename = isFileURI(filename) ? new URL(filename) : filename;
        var ret = fs.readFileSync(filename);
        return ret;
      };
      readAsync = async (filename, binary = true) => {
        filename = isFileURI(filename) ? new URL(filename) : filename;
        var ret = fs.readFileSync(filename, binary ? void 0 : "utf8");
        return ret;
      };
      if (process.argv.length > 1) {
        thisProgram = process.argv[1].replace(/\\/g, "/");
      }
      arguments_ = process.argv.slice(2);
      quit_ = (status, toThrow) => {
        process.exitCode = status;
        throw toThrow;
      };
    } else if (ENVIRONMENT_IS_WEB || ENVIRONMENT_IS_WORKER) {
      try {
        scriptDirectory = new URL(".", _scriptName).href;
      } catch {
      }
      {
        if (ENVIRONMENT_IS_WORKER) {
          readBinary = (url) => {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", url, false);
            xhr.responseType = "arraybuffer";
            xhr.send(null);
            return new Uint8Array(xhr.response);
          };
        }
        readAsync = async (url) => {
          if (isFileURI(url)) {
            return new Promise((resolve, reject) => {
              var xhr = new XMLHttpRequest();
              xhr.open("GET", url, true);
              xhr.responseType = "arraybuffer";
              xhr.onload = () => {
                if (xhr.status == 200 || xhr.status == 0 && xhr.response) {
                  resolve(xhr.response);
                  return;
                }
                reject(xhr.status);
              };
              xhr.onerror = reject;
              xhr.send(null);
            });
          }
          var response = await fetch(url, { credentials: "same-origin" });
          if (response.ok) {
            return response.arrayBuffer();
          }
          throw new Error(response.status + " : " + response.url);
        };
      }
    } else {
    }
    var out = console.log.bind(console);
    var err = console.error.bind(console);
    var wasmBinary;
    var wasmMemory;
    var ABORT = false;
    var HEAP8, HEAPU8, HEAP16, HEAPU16, HEAP32, HEAPU32, HEAPF32, HEAP64, HEAPU64, HEAPF64;
    var runtimeInitialized = false;
    var isFileURI = (filename) => filename.startsWith("file://");
    function updateMemoryViews() {
      var b = wasmMemory.buffer;
      HEAP8 = new Int8Array(b);
      HEAP16 = new Int16Array(b);
      Module2["HEAPU8"] = HEAPU8 = new Uint8Array(b);
      HEAPU16 = new Uint16Array(b);
      HEAP32 = new Int32Array(b);
      HEAPU32 = new Uint32Array(b);
      HEAPF32 = new Float32Array(b);
      HEAPF64 = new Float64Array(b);
      HEAP64 = new BigInt64Array(b);
      HEAPU64 = new BigUint64Array(b);
    }
    function preRun() {
      if (Module2["preRun"]) {
        if (typeof Module2["preRun"] == "function") Module2["preRun"] = [Module2["preRun"]];
        while (Module2["preRun"].length) {
          addOnPreRun(Module2["preRun"].shift());
        }
      }
      callRuntimeCallbacks(onPreRuns);
    }
    function initRuntime() {
      runtimeInitialized = true;
      if (!Module2["noFSInit"] && !FS.initialized) FS.init();
      TTY.init();
      wasmExports["S"]();
      FS.ignorePermissions = false;
    }
    function postRun() {
      if (Module2["postRun"]) {
        if (typeof Module2["postRun"] == "function") Module2["postRun"] = [Module2["postRun"]];
        while (Module2["postRun"].length) {
          addOnPostRun(Module2["postRun"].shift());
        }
      }
      callRuntimeCallbacks(onPostRuns);
    }
    var runDependencies = 0;
    var dependenciesFulfilled = null;
    function getUniqueRunDependency(id) {
      return id;
    }
    function addRunDependency(id) {
      runDependencies++;
      Module2["monitorRunDependencies"]?.(runDependencies);
    }
    function removeRunDependency(id) {
      runDependencies--;
      Module2["monitorRunDependencies"]?.(runDependencies);
      if (runDependencies == 0) {
        if (dependenciesFulfilled) {
          var callback = dependenciesFulfilled;
          dependenciesFulfilled = null;
          callback();
        }
      }
    }
    function abort(what) {
      Module2["onAbort"]?.(what);
      what = "Aborted(" + what + ")";
      err(what);
      ABORT = true;
      what += ". Build with -sASSERTIONS for more info.";
      var e = new WebAssembly.RuntimeError(what);
      readyPromiseReject(e);
      throw e;
    }
    var wasmBinaryFile;
    function findWasmBinary() {
      if (Module2["locateFile"]) {
        return locateFile("libraw.wasm");
      }
      return new URL("libraw.wasm", import.meta.url).href;
    }
    function getBinarySync(file) {
      if (file == wasmBinaryFile && wasmBinary) {
        return new Uint8Array(wasmBinary);
      }
      if (readBinary) {
        return readBinary(file);
      }
      throw "both async and sync fetching of the wasm failed";
    }
    async function getWasmBinary(binaryFile) {
      if (!wasmBinary) {
        try {
          var response = await readAsync(binaryFile);
          return new Uint8Array(response);
        } catch {
        }
      }
      return getBinarySync(binaryFile);
    }
    async function instantiateArrayBuffer(binaryFile, imports) {
      try {
        var binary = await getWasmBinary(binaryFile);
        var instance = await WebAssembly.instantiate(binary, imports);
        return instance;
      } catch (reason) {
        err(`failed to asynchronously prepare wasm: ${reason}`);
        abort(reason);
      }
    }
    async function instantiateAsync(binary, binaryFile, imports) {
      if (!binary && typeof WebAssembly.instantiateStreaming == "function" && !isFileURI(binaryFile) && !ENVIRONMENT_IS_NODE) {
        try {
          var response = fetch(binaryFile, { credentials: "same-origin" });
          var instantiationResult = await WebAssembly.instantiateStreaming(response, imports);
          return instantiationResult;
        } catch (reason) {
          err(`wasm streaming compile failed: ${reason}`);
          err("falling back to ArrayBuffer instantiation");
        }
      }
      return instantiateArrayBuffer(binaryFile, imports);
    }
    function getWasmImports() {
      return { a: wasmImports };
    }
    async function createWasm() {
      function receiveInstance(instance, module) {
        wasmExports = instance.exports;
        wasmMemory = wasmExports["R"];
        updateMemoryViews();
        wasmTable = wasmExports["T"];
        removeRunDependency("wasm-instantiate");
        return wasmExports;
      }
      addRunDependency("wasm-instantiate");
      function receiveInstantiationResult(result2) {
        return receiveInstance(result2["instance"]);
      }
      var info = getWasmImports();
      if (Module2["instantiateWasm"]) {
        return new Promise((resolve, reject) => {
          Module2["instantiateWasm"](info, (mod, inst) => {
            resolve(receiveInstance(mod, inst));
          });
        });
      }
      wasmBinaryFile ??= findWasmBinary();
      try {
        var result = await instantiateAsync(wasmBinary, wasmBinaryFile, info);
        var exports = receiveInstantiationResult(result);
        return exports;
      } catch (e) {
        readyPromiseReject(e);
        return Promise.reject(e);
      }
    }
    class ExitStatus {
      name = "ExitStatus";
      constructor(status) {
        this.message = `Program terminated with exit(${status})`;
        this.status = status;
      }
    }
    var callRuntimeCallbacks = (callbacks) => {
      while (callbacks.length > 0) {
        callbacks.shift()(Module2);
      }
    };
    var onPostRuns = [];
    var addOnPostRun = (cb) => onPostRuns.push(cb);
    var onPreRuns = [];
    var addOnPreRun = (cb) => onPreRuns.push(cb);
    var noExitRuntime = true;
    var stackRestore = (val) => __emscripten_stack_restore(val);
    var stackSave = () => _emscripten_stack_get_current();
    var exceptionCaught = [];
    var uncaughtExceptionCount = 0;
    var ___cxa_begin_catch = (ptr2) => {
      var info = new ExceptionInfo(ptr2);
      if (!info.get_caught()) {
        info.set_caught(true);
        uncaughtExceptionCount--;
      }
      info.set_rethrown(false);
      exceptionCaught.push(info);
      ___cxa_increment_exception_refcount(ptr2);
      return ___cxa_get_exception_ptr(ptr2);
    };
    var exceptionLast = 0;
    var ___cxa_end_catch = () => {
      _setThrew(0, 0);
      var info = exceptionCaught.pop();
      ___cxa_decrement_exception_refcount(info.excPtr);
      exceptionLast = 0;
    };
    class ExceptionInfo {
      constructor(excPtr) {
        this.excPtr = excPtr;
        this.ptr = excPtr - 24;
      }
      set_type(type) {
        HEAPU32[this.ptr + 4 >> 2] = type;
      }
      get_type() {
        return HEAPU32[this.ptr + 4 >> 2];
      }
      set_destructor(destructor) {
        HEAPU32[this.ptr + 8 >> 2] = destructor;
      }
      get_destructor() {
        return HEAPU32[this.ptr + 8 >> 2];
      }
      set_caught(caught) {
        caught = caught ? 1 : 0;
        HEAP8[this.ptr + 12] = caught;
      }
      get_caught() {
        return HEAP8[this.ptr + 12] != 0;
      }
      set_rethrown(rethrown) {
        rethrown = rethrown ? 1 : 0;
        HEAP8[this.ptr + 13] = rethrown;
      }
      get_rethrown() {
        return HEAP8[this.ptr + 13] != 0;
      }
      init(type, destructor) {
        this.set_adjusted_ptr(0);
        this.set_type(type);
        this.set_destructor(destructor);
      }
      set_adjusted_ptr(adjustedPtr) {
        HEAPU32[this.ptr + 16 >> 2] = adjustedPtr;
      }
      get_adjusted_ptr() {
        return HEAPU32[this.ptr + 16 >> 2];
      }
    }
    var setTempRet0 = (val) => __emscripten_tempret_set(val);
    var findMatchingCatch = (args) => {
      var thrown = exceptionLast;
      if (!thrown) {
        setTempRet0(0);
        return 0;
      }
      var info = new ExceptionInfo(thrown);
      info.set_adjusted_ptr(thrown);
      var thrownType = info.get_type();
      if (!thrownType) {
        setTempRet0(0);
        return thrown;
      }
      for (var caughtType of args) {
        if (caughtType === 0 || caughtType === thrownType) {
          break;
        }
        var adjusted_ptr_addr = info.ptr + 16;
        if (___cxa_can_catch(caughtType, thrownType, adjusted_ptr_addr)) {
          setTempRet0(caughtType);
          return thrown;
        }
      }
      setTempRet0(thrownType);
      return thrown;
    };
    var ___cxa_find_matching_catch_2 = () => findMatchingCatch([]);
    var ___cxa_find_matching_catch_3 = (arg0) => findMatchingCatch([arg0]);
    var ___cxa_find_matching_catch_4 = (arg0, arg1) => findMatchingCatch([arg0, arg1]);
    var ___cxa_find_matching_catch_5 = (arg0, arg1, arg2) => findMatchingCatch([arg0, arg1, arg2]);
    var ___cxa_rethrow = () => {
      var info = exceptionCaught.pop();
      if (!info) {
        abort("no exception to throw");
      }
      var ptr2 = info.excPtr;
      if (!info.get_rethrown()) {
        exceptionCaught.push(info);
        info.set_rethrown(true);
        info.set_caught(false);
        uncaughtExceptionCount++;
      }
      exceptionLast = ptr2;
      throw exceptionLast;
    };
    var ___cxa_throw = (ptr2, type, destructor) => {
      var info = new ExceptionInfo(ptr2);
      info.init(type, destructor);
      exceptionLast = ptr2;
      uncaughtExceptionCount++;
      throw exceptionLast;
    };
    var ___resumeException = (ptr2) => {
      if (!exceptionLast) {
        exceptionLast = ptr2;
      }
      throw exceptionLast;
    };
    var syscallGetVarargI = () => {
      var ret = HEAP32[+SYSCALLS.varargs >> 2];
      SYSCALLS.varargs += 4;
      return ret;
    };
    var syscallGetVarargP = syscallGetVarargI;
    var PATH = { isAbs: (path) => path.charAt(0) === "/", splitPath: (filename) => {
      var splitPathRe = /^(\/?|)([\s\S]*?)((?:\.{1,2}|[^\/]+?|)(\.[^.\/]*|))(?:[\/]*)$/;
      return splitPathRe.exec(filename).slice(1);
    }, normalizeArray: (parts, allowAboveRoot) => {
      var up = 0;
      for (var i = parts.length - 1; i >= 0; i--) {
        var last = parts[i];
        if (last === ".") {
          parts.splice(i, 1);
        } else if (last === "..") {
          parts.splice(i, 1);
          up++;
        } else if (up) {
          parts.splice(i, 1);
          up--;
        }
      }
      if (allowAboveRoot) {
        for (; up; up--) {
          parts.unshift("..");
        }
      }
      return parts;
    }, normalize: (path) => {
      var isAbsolute = PATH.isAbs(path), trailingSlash = path.slice(-1) === "/";
      path = PATH.normalizeArray(path.split("/").filter((p) => !!p), !isAbsolute).join("/");
      if (!path && !isAbsolute) {
        path = ".";
      }
      if (path && trailingSlash) {
        path += "/";
      }
      return (isAbsolute ? "/" : "") + path;
    }, dirname: (path) => {
      var result = PATH.splitPath(path), root = result[0], dir = result[1];
      if (!root && !dir) {
        return ".";
      }
      if (dir) {
        dir = dir.slice(0, -1);
      }
      return root + dir;
    }, basename: (path) => path && path.match(/([^\/]+|\/)\/*$/)[1], join: (...paths) => PATH.normalize(paths.join("/")), join2: (l, r) => PATH.normalize(l + "/" + r) };
    var initRandomFill = () => {
      if (ENVIRONMENT_IS_NODE) {
        var nodeCrypto = require2("crypto");
        return (view2) => nodeCrypto.randomFillSync(view2);
      }
      return (view2) => crypto.getRandomValues(view2);
    };
    var randomFill = (view2) => {
      (randomFill = initRandomFill())(view2);
    };
    var PATH_FS = { resolve: (...args) => {
      var resolvedPath = "", resolvedAbsolute = false;
      for (var i = args.length - 1; i >= -1 && !resolvedAbsolute; i--) {
        var path = i >= 0 ? args[i] : FS.cwd();
        if (typeof path != "string") {
          throw new TypeError("Arguments to path.resolve must be strings");
        } else if (!path) {
          return "";
        }
        resolvedPath = path + "/" + resolvedPath;
        resolvedAbsolute = PATH.isAbs(path);
      }
      resolvedPath = PATH.normalizeArray(resolvedPath.split("/").filter((p) => !!p), !resolvedAbsolute).join("/");
      return (resolvedAbsolute ? "/" : "") + resolvedPath || ".";
    }, relative: (from, to) => {
      from = PATH_FS.resolve(from).slice(1);
      to = PATH_FS.resolve(to).slice(1);
      function trim(arr) {
        var start = 0;
        for (; start < arr.length; start++) {
          if (arr[start] !== "") break;
        }
        var end = arr.length - 1;
        for (; end >= 0; end--) {
          if (arr[end] !== "") break;
        }
        if (start > end) return [];
        return arr.slice(start, end - start + 1);
      }
      var fromParts = trim(from.split("/"));
      var toParts = trim(to.split("/"));
      var length = Math.min(fromParts.length, toParts.length);
      var samePartsLength = length;
      for (var i = 0; i < length; i++) {
        if (fromParts[i] !== toParts[i]) {
          samePartsLength = i;
          break;
        }
      }
      var outputParts = [];
      for (var i = samePartsLength; i < fromParts.length; i++) {
        outputParts.push("..");
      }
      outputParts = outputParts.concat(toParts.slice(samePartsLength));
      return outputParts.join("/");
    } };
    var UTF8Decoder = typeof TextDecoder != "undefined" ? new TextDecoder() : void 0;
    var UTF8ArrayToString = (heapOrArray, idx = 0, maxBytesToRead = NaN) => {
      var endIdx = idx + maxBytesToRead;
      var endPtr = idx;
      while (heapOrArray[endPtr] && !(endPtr >= endIdx)) ++endPtr;
      if (endPtr - idx > 16 && heapOrArray.buffer && UTF8Decoder) {
        return UTF8Decoder.decode(heapOrArray.subarray(idx, endPtr));
      }
      var str = "";
      while (idx < endPtr) {
        var u0 = heapOrArray[idx++];
        if (!(u0 & 128)) {
          str += String.fromCharCode(u0);
          continue;
        }
        var u1 = heapOrArray[idx++] & 63;
        if ((u0 & 224) == 192) {
          str += String.fromCharCode((u0 & 31) << 6 | u1);
          continue;
        }
        var u2 = heapOrArray[idx++] & 63;
        if ((u0 & 240) == 224) {
          u0 = (u0 & 15) << 12 | u1 << 6 | u2;
        } else {
          u0 = (u0 & 7) << 18 | u1 << 12 | u2 << 6 | heapOrArray[idx++] & 63;
        }
        if (u0 < 65536) {
          str += String.fromCharCode(u0);
        } else {
          var ch = u0 - 65536;
          str += String.fromCharCode(55296 | ch >> 10, 56320 | ch & 1023);
        }
      }
      return str;
    };
    var FS_stdin_getChar_buffer = [];
    var lengthBytesUTF8 = (str) => {
      var len = 0;
      for (var i = 0; i < str.length; ++i) {
        var c = str.charCodeAt(i);
        if (c <= 127) {
          len++;
        } else if (c <= 2047) {
          len += 2;
        } else if (c >= 55296 && c <= 57343) {
          len += 4;
          ++i;
        } else {
          len += 3;
        }
      }
      return len;
    };
    var stringToUTF8Array = (str, heap, outIdx, maxBytesToWrite) => {
      if (!(maxBytesToWrite > 0)) return 0;
      var startIdx = outIdx;
      var endIdx = outIdx + maxBytesToWrite - 1;
      for (var i = 0; i < str.length; ++i) {
        var u = str.charCodeAt(i);
        if (u >= 55296 && u <= 57343) {
          var u1 = str.charCodeAt(++i);
          u = 65536 + ((u & 1023) << 10) | u1 & 1023;
        }
        if (u <= 127) {
          if (outIdx >= endIdx) break;
          heap[outIdx++] = u;
        } else if (u <= 2047) {
          if (outIdx + 1 >= endIdx) break;
          heap[outIdx++] = 192 | u >> 6;
          heap[outIdx++] = 128 | u & 63;
        } else if (u <= 65535) {
          if (outIdx + 2 >= endIdx) break;
          heap[outIdx++] = 224 | u >> 12;
          heap[outIdx++] = 128 | u >> 6 & 63;
          heap[outIdx++] = 128 | u & 63;
        } else {
          if (outIdx + 3 >= endIdx) break;
          heap[outIdx++] = 240 | u >> 18;
          heap[outIdx++] = 128 | u >> 12 & 63;
          heap[outIdx++] = 128 | u >> 6 & 63;
          heap[outIdx++] = 128 | u & 63;
        }
      }
      heap[outIdx] = 0;
      return outIdx - startIdx;
    };
    var intArrayFromString = (stringy, dontAddNull, length) => {
      var len = length > 0 ? length : lengthBytesUTF8(stringy) + 1;
      var u8array = new Array(len);
      var numBytesWritten = stringToUTF8Array(stringy, u8array, 0, u8array.length);
      if (dontAddNull) u8array.length = numBytesWritten;
      return u8array;
    };
    var FS_stdin_getChar = () => {
      if (!FS_stdin_getChar_buffer.length) {
        var result = null;
        if (ENVIRONMENT_IS_NODE) {
          var BUFSIZE = 256;
          var buf = Buffer.alloc(BUFSIZE);
          var bytesRead = 0;
          var fd = process.stdin.fd;
          try {
            bytesRead = fs.readSync(fd, buf, 0, BUFSIZE);
          } catch (e) {
            if (e.toString().includes("EOF")) bytesRead = 0;
            else throw e;
          }
          if (bytesRead > 0) {
            result = buf.slice(0, bytesRead).toString("utf-8");
          }
        } else if (typeof window != "undefined" && typeof window.prompt == "function") {
          result = window.prompt("Input: ");
          if (result !== null) {
            result += "\n";
          }
        } else {
        }
        if (!result) {
          return null;
        }
        FS_stdin_getChar_buffer = intArrayFromString(result, true);
      }
      return FS_stdin_getChar_buffer.shift();
    };
    var TTY = { ttys: [], init() {
    }, shutdown() {
    }, register(dev, ops) {
      TTY.ttys[dev] = { input: [], output: [], ops };
      FS.registerDevice(dev, TTY.stream_ops);
    }, stream_ops: { open(stream) {
      var tty = TTY.ttys[stream.node.rdev];
      if (!tty) {
        throw new FS.ErrnoError(43);
      }
      stream.tty = tty;
      stream.seekable = false;
    }, close(stream) {
      stream.tty.ops.fsync(stream.tty);
    }, fsync(stream) {
      stream.tty.ops.fsync(stream.tty);
    }, read(stream, buffer, offset, length, pos) {
      if (!stream.tty || !stream.tty.ops.get_char) {
        throw new FS.ErrnoError(60);
      }
      var bytesRead = 0;
      for (var i = 0; i < length; i++) {
        var result;
        try {
          result = stream.tty.ops.get_char(stream.tty);
        } catch (e) {
          throw new FS.ErrnoError(29);
        }
        if (result === void 0 && bytesRead === 0) {
          throw new FS.ErrnoError(6);
        }
        if (result === null || result === void 0) break;
        bytesRead++;
        buffer[offset + i] = result;
      }
      if (bytesRead) {
        stream.node.atime = Date.now();
      }
      return bytesRead;
    }, write(stream, buffer, offset, length, pos) {
      if (!stream.tty || !stream.tty.ops.put_char) {
        throw new FS.ErrnoError(60);
      }
      try {
        for (var i = 0; i < length; i++) {
          stream.tty.ops.put_char(stream.tty, buffer[offset + i]);
        }
      } catch (e) {
        throw new FS.ErrnoError(29);
      }
      if (length) {
        stream.node.mtime = stream.node.ctime = Date.now();
      }
      return i;
    } }, default_tty_ops: { get_char(tty) {
      return FS_stdin_getChar();
    }, put_char(tty, val) {
      if (val === null || val === 10) {
        out(UTF8ArrayToString(tty.output));
        tty.output = [];
      } else {
        if (val != 0) tty.output.push(val);
      }
    }, fsync(tty) {
      if (tty.output?.length > 0) {
        out(UTF8ArrayToString(tty.output));
        tty.output = [];
      }
    }, ioctl_tcgets(tty) {
      return { c_iflag: 25856, c_oflag: 5, c_cflag: 191, c_lflag: 35387, c_cc: [3, 28, 127, 21, 4, 0, 1, 0, 17, 19, 26, 0, 18, 15, 23, 22, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] };
    }, ioctl_tcsets(tty, optional_actions, data) {
      return 0;
    }, ioctl_tiocgwinsz(tty) {
      return [24, 80];
    } }, default_tty1_ops: { put_char(tty, val) {
      if (val === null || val === 10) {
        err(UTF8ArrayToString(tty.output));
        tty.output = [];
      } else {
        if (val != 0) tty.output.push(val);
      }
    }, fsync(tty) {
      if (tty.output?.length > 0) {
        err(UTF8ArrayToString(tty.output));
        tty.output = [];
      }
    } } };
    var mmapAlloc = (size) => {
      abort();
    };
    var MEMFS = { ops_table: null, mount(mount) {
      return MEMFS.createNode(null, "/", 16895, 0);
    }, createNode(parent, name, mode, dev) {
      if (FS.isBlkdev(mode) || FS.isFIFO(mode)) {
        throw new FS.ErrnoError(63);
      }
      MEMFS.ops_table ||= { dir: { node: { getattr: MEMFS.node_ops.getattr, setattr: MEMFS.node_ops.setattr, lookup: MEMFS.node_ops.lookup, mknod: MEMFS.node_ops.mknod, rename: MEMFS.node_ops.rename, unlink: MEMFS.node_ops.unlink, rmdir: MEMFS.node_ops.rmdir, readdir: MEMFS.node_ops.readdir, symlink: MEMFS.node_ops.symlink }, stream: { llseek: MEMFS.stream_ops.llseek } }, file: { node: { getattr: MEMFS.node_ops.getattr, setattr: MEMFS.node_ops.setattr }, stream: { llseek: MEMFS.stream_ops.llseek, read: MEMFS.stream_ops.read, write: MEMFS.stream_ops.write, mmap: MEMFS.stream_ops.mmap, msync: MEMFS.stream_ops.msync } }, link: { node: { getattr: MEMFS.node_ops.getattr, setattr: MEMFS.node_ops.setattr, readlink: MEMFS.node_ops.readlink }, stream: {} }, chrdev: { node: { getattr: MEMFS.node_ops.getattr, setattr: MEMFS.node_ops.setattr }, stream: FS.chrdev_stream_ops } };
      var node = FS.createNode(parent, name, mode, dev);
      if (FS.isDir(node.mode)) {
        node.node_ops = MEMFS.ops_table.dir.node;
        node.stream_ops = MEMFS.ops_table.dir.stream;
        node.contents = {};
      } else if (FS.isFile(node.mode)) {
        node.node_ops = MEMFS.ops_table.file.node;
        node.stream_ops = MEMFS.ops_table.file.stream;
        node.usedBytes = 0;
        node.contents = null;
      } else if (FS.isLink(node.mode)) {
        node.node_ops = MEMFS.ops_table.link.node;
        node.stream_ops = MEMFS.ops_table.link.stream;
      } else if (FS.isChrdev(node.mode)) {
        node.node_ops = MEMFS.ops_table.chrdev.node;
        node.stream_ops = MEMFS.ops_table.chrdev.stream;
      }
      node.atime = node.mtime = node.ctime = Date.now();
      if (parent) {
        parent.contents[name] = node;
        parent.atime = parent.mtime = parent.ctime = node.atime;
      }
      return node;
    }, getFileDataAsTypedArray(node) {
      if (!node.contents) return new Uint8Array(0);
      if (node.contents.subarray) return node.contents.subarray(0, node.usedBytes);
      return new Uint8Array(node.contents);
    }, expandFileStorage(node, newCapacity) {
      var prevCapacity = node.contents ? node.contents.length : 0;
      if (prevCapacity >= newCapacity) return;
      var CAPACITY_DOUBLING_MAX = 1024 * 1024;
      newCapacity = Math.max(newCapacity, prevCapacity * (prevCapacity < CAPACITY_DOUBLING_MAX ? 2 : 1.125) >>> 0);
      if (prevCapacity != 0) newCapacity = Math.max(newCapacity, 256);
      var oldContents = node.contents;
      node.contents = new Uint8Array(newCapacity);
      if (node.usedBytes > 0) node.contents.set(oldContents.subarray(0, node.usedBytes), 0);
    }, resizeFileStorage(node, newSize) {
      if (node.usedBytes == newSize) return;
      if (newSize == 0) {
        node.contents = null;
        node.usedBytes = 0;
      } else {
        var oldContents = node.contents;
        node.contents = new Uint8Array(newSize);
        if (oldContents) {
          node.contents.set(oldContents.subarray(0, Math.min(newSize, node.usedBytes)));
        }
        node.usedBytes = newSize;
      }
    }, node_ops: { getattr(node) {
      var attr = {};
      attr.dev = FS.isChrdev(node.mode) ? node.id : 1;
      attr.ino = node.id;
      attr.mode = node.mode;
      attr.nlink = 1;
      attr.uid = 0;
      attr.gid = 0;
      attr.rdev = node.rdev;
      if (FS.isDir(node.mode)) {
        attr.size = 4096;
      } else if (FS.isFile(node.mode)) {
        attr.size = node.usedBytes;
      } else if (FS.isLink(node.mode)) {
        attr.size = node.link.length;
      } else {
        attr.size = 0;
      }
      attr.atime = new Date(node.atime);
      attr.mtime = new Date(node.mtime);
      attr.ctime = new Date(node.ctime);
      attr.blksize = 4096;
      attr.blocks = Math.ceil(attr.size / attr.blksize);
      return attr;
    }, setattr(node, attr) {
      for (const key of ["mode", "atime", "mtime", "ctime"]) {
        if (attr[key] != null) {
          node[key] = attr[key];
        }
      }
      if (attr.size !== void 0) {
        MEMFS.resizeFileStorage(node, attr.size);
      }
    }, lookup(parent, name) {
      throw MEMFS.doesNotExistError;
    }, mknod(parent, name, mode, dev) {
      return MEMFS.createNode(parent, name, mode, dev);
    }, rename(old_node, new_dir, new_name) {
      var new_node;
      try {
        new_node = FS.lookupNode(new_dir, new_name);
      } catch (e) {
      }
      if (new_node) {
        if (FS.isDir(old_node.mode)) {
          for (var i in new_node.contents) {
            throw new FS.ErrnoError(55);
          }
        }
        FS.hashRemoveNode(new_node);
      }
      delete old_node.parent.contents[old_node.name];
      new_dir.contents[new_name] = old_node;
      old_node.name = new_name;
      new_dir.ctime = new_dir.mtime = old_node.parent.ctime = old_node.parent.mtime = Date.now();
    }, unlink(parent, name) {
      delete parent.contents[name];
      parent.ctime = parent.mtime = Date.now();
    }, rmdir(parent, name) {
      var node = FS.lookupNode(parent, name);
      for (var i in node.contents) {
        throw new FS.ErrnoError(55);
      }
      delete parent.contents[name];
      parent.ctime = parent.mtime = Date.now();
    }, readdir(node) {
      return [".", "..", ...Object.keys(node.contents)];
    }, symlink(parent, newname, oldpath) {
      var node = MEMFS.createNode(parent, newname, 511 | 40960, 0);
      node.link = oldpath;
      return node;
    }, readlink(node) {
      if (!FS.isLink(node.mode)) {
        throw new FS.ErrnoError(28);
      }
      return node.link;
    } }, stream_ops: { read(stream, buffer, offset, length, position) {
      var contents = stream.node.contents;
      if (position >= stream.node.usedBytes) return 0;
      var size = Math.min(stream.node.usedBytes - position, length);
      if (size > 8 && contents.subarray) {
        buffer.set(contents.subarray(position, position + size), offset);
      } else {
        for (var i = 0; i < size; i++) buffer[offset + i] = contents[position + i];
      }
      return size;
    }, write(stream, buffer, offset, length, position, canOwn) {
      if (buffer.buffer === HEAP8.buffer) {
        canOwn = false;
      }
      if (!length) return 0;
      var node = stream.node;
      node.mtime = node.ctime = Date.now();
      if (buffer.subarray && (!node.contents || node.contents.subarray)) {
        if (canOwn) {
          node.contents = buffer.subarray(offset, offset + length);
          node.usedBytes = length;
          return length;
        } else if (node.usedBytes === 0 && position === 0) {
          node.contents = buffer.slice(offset, offset + length);
          node.usedBytes = length;
          return length;
        } else if (position + length <= node.usedBytes) {
          node.contents.set(buffer.subarray(offset, offset + length), position);
          return length;
        }
      }
      MEMFS.expandFileStorage(node, position + length);
      if (node.contents.subarray && buffer.subarray) {
        node.contents.set(buffer.subarray(offset, offset + length), position);
      } else {
        for (var i = 0; i < length; i++) {
          node.contents[position + i] = buffer[offset + i];
        }
      }
      node.usedBytes = Math.max(node.usedBytes, position + length);
      return length;
    }, llseek(stream, offset, whence) {
      var position = offset;
      if (whence === 1) {
        position += stream.position;
      } else if (whence === 2) {
        if (FS.isFile(stream.node.mode)) {
          position += stream.node.usedBytes;
        }
      }
      if (position < 0) {
        throw new FS.ErrnoError(28);
      }
      return position;
    }, mmap(stream, length, position, prot, flags) {
      if (!FS.isFile(stream.node.mode)) {
        throw new FS.ErrnoError(43);
      }
      var ptr2;
      var allocated;
      var contents = stream.node.contents;
      if (!(flags & 2) && contents && contents.buffer === HEAP8.buffer) {
        allocated = false;
        ptr2 = contents.byteOffset;
      } else {
        allocated = true;
        ptr2 = mmapAlloc(length);
        if (!ptr2) {
          throw new FS.ErrnoError(48);
        }
        if (contents) {
          if (position > 0 || position + length < contents.length) {
            if (contents.subarray) {
              contents = contents.subarray(position, position + length);
            } else {
              contents = Array.prototype.slice.call(contents, position, position + length);
            }
          }
          HEAP8.set(contents, ptr2);
        }
      }
      return { ptr: ptr2, allocated };
    }, msync(stream, buffer, offset, length, mmapFlags) {
      MEMFS.stream_ops.write(stream, buffer, 0, length, offset, false);
      return 0;
    } } };
    var asyncLoad = async (url) => {
      var arrayBuffer = await readAsync(url);
      return new Uint8Array(arrayBuffer);
    };
    var FS_createDataFile = (...args) => FS.createDataFile(...args);
    var preloadPlugins = [];
    var FS_handledByPreloadPlugin = (byteArray, fullname, finish, onerror) => {
      if (typeof Browser != "undefined") Browser.init();
      var handled = false;
      preloadPlugins.forEach((plugin) => {
        if (handled) return;
        if (plugin["canHandle"](fullname)) {
          plugin["handle"](byteArray, fullname, finish, onerror);
          handled = true;
        }
      });
      return handled;
    };
    var FS_createPreloadedFile = (parent, name, url, canRead, canWrite, onload, onerror, dontCreateFile, canOwn, preFinish) => {
      var fullname = name ? PATH_FS.resolve(PATH.join2(parent, name)) : parent;
      var dep = getUniqueRunDependency(`cp ${fullname}`);
      function processData(byteArray) {
        function finish(byteArray2) {
          preFinish?.();
          if (!dontCreateFile) {
            FS_createDataFile(parent, name, byteArray2, canRead, canWrite, canOwn);
          }
          onload?.();
          removeRunDependency(dep);
        }
        if (FS_handledByPreloadPlugin(byteArray, fullname, finish, () => {
          onerror?.();
          removeRunDependency(dep);
        })) {
          return;
        }
        finish(byteArray);
      }
      addRunDependency(dep);
      if (typeof url == "string") {
        asyncLoad(url).then(processData, onerror);
      } else {
        processData(url);
      }
    };
    var FS_modeStringToFlags = (str) => {
      var flagModes = { r: 0, "r+": 2, w: 512 | 64 | 1, "w+": 512 | 64 | 2, a: 1024 | 64 | 1, "a+": 1024 | 64 | 2 };
      var flags = flagModes[str];
      if (typeof flags == "undefined") {
        throw new Error(`Unknown file open mode: ${str}`);
      }
      return flags;
    };
    var FS_getMode = (canRead, canWrite) => {
      var mode = 0;
      if (canRead) mode |= 292 | 73;
      if (canWrite) mode |= 146;
      return mode;
    };
    var FS = { root: null, mounts: [], devices: {}, streams: [], nextInode: 1, nameTable: null, currentPath: "/", initialized: false, ignorePermissions: true, filesystems: null, syncFSRequests: 0, readFiles: {}, ErrnoError: class {
      name = "ErrnoError";
      constructor(errno) {
        this.errno = errno;
      }
    }, FSStream: class {
      shared = {};
      get object() {
        return this.node;
      }
      set object(val) {
        this.node = val;
      }
      get isRead() {
        return (this.flags & 2097155) !== 1;
      }
      get isWrite() {
        return (this.flags & 2097155) !== 0;
      }
      get isAppend() {
        return this.flags & 1024;
      }
      get flags() {
        return this.shared.flags;
      }
      set flags(val) {
        this.shared.flags = val;
      }
      get position() {
        return this.shared.position;
      }
      set position(val) {
        this.shared.position = val;
      }
    }, FSNode: class {
      node_ops = {};
      stream_ops = {};
      readMode = 292 | 73;
      writeMode = 146;
      mounted = null;
      constructor(parent, name, mode, rdev) {
        if (!parent) {
          parent = this;
        }
        this.parent = parent;
        this.mount = parent.mount;
        this.id = FS.nextInode++;
        this.name = name;
        this.mode = mode;
        this.rdev = rdev;
        this.atime = this.mtime = this.ctime = Date.now();
      }
      get read() {
        return (this.mode & this.readMode) === this.readMode;
      }
      set read(val) {
        val ? this.mode |= this.readMode : this.mode &= ~this.readMode;
      }
      get write() {
        return (this.mode & this.writeMode) === this.writeMode;
      }
      set write(val) {
        val ? this.mode |= this.writeMode : this.mode &= ~this.writeMode;
      }
      get isFolder() {
        return FS.isDir(this.mode);
      }
      get isDevice() {
        return FS.isChrdev(this.mode);
      }
    }, lookupPath(path, opts = {}) {
      if (!path) {
        throw new FS.ErrnoError(44);
      }
      opts.follow_mount ??= true;
      if (!PATH.isAbs(path)) {
        path = FS.cwd() + "/" + path;
      }
      linkloop: for (var nlinks = 0; nlinks < 40; nlinks++) {
        var parts = path.split("/").filter((p) => !!p);
        var current = FS.root;
        var current_path = "/";
        for (var i = 0; i < parts.length; i++) {
          var islast = i === parts.length - 1;
          if (islast && opts.parent) {
            break;
          }
          if (parts[i] === ".") {
            continue;
          }
          if (parts[i] === "..") {
            current_path = PATH.dirname(current_path);
            if (FS.isRoot(current)) {
              path = current_path + "/" + parts.slice(i + 1).join("/");
              continue linkloop;
            } else {
              current = current.parent;
            }
            continue;
          }
          current_path = PATH.join2(current_path, parts[i]);
          try {
            current = FS.lookupNode(current, parts[i]);
          } catch (e) {
            if (e?.errno === 44 && islast && opts.noent_okay) {
              return { path: current_path };
            }
            throw e;
          }
          if (FS.isMountpoint(current) && (!islast || opts.follow_mount)) {
            current = current.mounted.root;
          }
          if (FS.isLink(current.mode) && (!islast || opts.follow)) {
            if (!current.node_ops.readlink) {
              throw new FS.ErrnoError(52);
            }
            var link = current.node_ops.readlink(current);
            if (!PATH.isAbs(link)) {
              link = PATH.dirname(current_path) + "/" + link;
            }
            path = link + "/" + parts.slice(i + 1).join("/");
            continue linkloop;
          }
        }
        return { path: current_path, node: current };
      }
      throw new FS.ErrnoError(32);
    }, getPath(node) {
      var path;
      while (true) {
        if (FS.isRoot(node)) {
          var mount = node.mount.mountpoint;
          if (!path) return mount;
          return mount[mount.length - 1] !== "/" ? `${mount}/${path}` : mount + path;
        }
        path = path ? `${node.name}/${path}` : node.name;
        node = node.parent;
      }
    }, hashName(parentid, name) {
      var hash = 0;
      for (var i = 0; i < name.length; i++) {
        hash = (hash << 5) - hash + name.charCodeAt(i) | 0;
      }
      return (parentid + hash >>> 0) % FS.nameTable.length;
    }, hashAddNode(node) {
      var hash = FS.hashName(node.parent.id, node.name);
      node.name_next = FS.nameTable[hash];
      FS.nameTable[hash] = node;
    }, hashRemoveNode(node) {
      var hash = FS.hashName(node.parent.id, node.name);
      if (FS.nameTable[hash] === node) {
        FS.nameTable[hash] = node.name_next;
      } else {
        var current = FS.nameTable[hash];
        while (current) {
          if (current.name_next === node) {
            current.name_next = node.name_next;
            break;
          }
          current = current.name_next;
        }
      }
    }, lookupNode(parent, name) {
      var errCode = FS.mayLookup(parent);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      var hash = FS.hashName(parent.id, name);
      for (var node = FS.nameTable[hash]; node; node = node.name_next) {
        var nodeName = node.name;
        if (node.parent.id === parent.id && nodeName === name) {
          return node;
        }
      }
      return FS.lookup(parent, name);
    }, createNode(parent, name, mode, rdev) {
      var node = new FS.FSNode(parent, name, mode, rdev);
      FS.hashAddNode(node);
      return node;
    }, destroyNode(node) {
      FS.hashRemoveNode(node);
    }, isRoot(node) {
      return node === node.parent;
    }, isMountpoint(node) {
      return !!node.mounted;
    }, isFile(mode) {
      return (mode & 61440) === 32768;
    }, isDir(mode) {
      return (mode & 61440) === 16384;
    }, isLink(mode) {
      return (mode & 61440) === 40960;
    }, isChrdev(mode) {
      return (mode & 61440) === 8192;
    }, isBlkdev(mode) {
      return (mode & 61440) === 24576;
    }, isFIFO(mode) {
      return (mode & 61440) === 4096;
    }, isSocket(mode) {
      return (mode & 49152) === 49152;
    }, flagsToPermissionString(flag) {
      var perms = ["r", "w", "rw"][flag & 3];
      if (flag & 512) {
        perms += "w";
      }
      return perms;
    }, nodePermissions(node, perms) {
      if (FS.ignorePermissions) {
        return 0;
      }
      if (perms.includes("r") && !(node.mode & 292)) {
        return 2;
      } else if (perms.includes("w") && !(node.mode & 146)) {
        return 2;
      } else if (perms.includes("x") && !(node.mode & 73)) {
        return 2;
      }
      return 0;
    }, mayLookup(dir) {
      if (!FS.isDir(dir.mode)) return 54;
      var errCode = FS.nodePermissions(dir, "x");
      if (errCode) return errCode;
      if (!dir.node_ops.lookup) return 2;
      return 0;
    }, mayCreate(dir, name) {
      if (!FS.isDir(dir.mode)) {
        return 54;
      }
      try {
        var node = FS.lookupNode(dir, name);
        return 20;
      } catch (e) {
      }
      return FS.nodePermissions(dir, "wx");
    }, mayDelete(dir, name, isdir) {
      var node;
      try {
        node = FS.lookupNode(dir, name);
      } catch (e) {
        return e.errno;
      }
      var errCode = FS.nodePermissions(dir, "wx");
      if (errCode) {
        return errCode;
      }
      if (isdir) {
        if (!FS.isDir(node.mode)) {
          return 54;
        }
        if (FS.isRoot(node) || FS.getPath(node) === FS.cwd()) {
          return 10;
        }
      } else {
        if (FS.isDir(node.mode)) {
          return 31;
        }
      }
      return 0;
    }, mayOpen(node, flags) {
      if (!node) {
        return 44;
      }
      if (FS.isLink(node.mode)) {
        return 32;
      } else if (FS.isDir(node.mode)) {
        if (FS.flagsToPermissionString(flags) !== "r" || flags & (512 | 64)) {
          return 31;
        }
      }
      return FS.nodePermissions(node, FS.flagsToPermissionString(flags));
    }, checkOpExists(op, err2) {
      if (!op) {
        throw new FS.ErrnoError(err2);
      }
      return op;
    }, MAX_OPEN_FDS: 4096, nextfd() {
      for (var fd = 0; fd <= FS.MAX_OPEN_FDS; fd++) {
        if (!FS.streams[fd]) {
          return fd;
        }
      }
      throw new FS.ErrnoError(33);
    }, getStreamChecked(fd) {
      var stream = FS.getStream(fd);
      if (!stream) {
        throw new FS.ErrnoError(8);
      }
      return stream;
    }, getStream: (fd) => FS.streams[fd], createStream(stream, fd = -1) {
      stream = Object.assign(new FS.FSStream(), stream);
      if (fd == -1) {
        fd = FS.nextfd();
      }
      stream.fd = fd;
      FS.streams[fd] = stream;
      return stream;
    }, closeStream(fd) {
      FS.streams[fd] = null;
    }, dupStream(origStream, fd = -1) {
      var stream = FS.createStream(origStream, fd);
      stream.stream_ops?.dup?.(stream);
      return stream;
    }, doSetAttr(stream, node, attr) {
      var setattr = stream?.stream_ops.setattr;
      var arg = setattr ? stream : node;
      setattr ??= node.node_ops.setattr;
      FS.checkOpExists(setattr, 63);
      setattr(arg, attr);
    }, chrdev_stream_ops: { open(stream) {
      var device = FS.getDevice(stream.node.rdev);
      stream.stream_ops = device.stream_ops;
      stream.stream_ops.open?.(stream);
    }, llseek() {
      throw new FS.ErrnoError(70);
    } }, major: (dev) => dev >> 8, minor: (dev) => dev & 255, makedev: (ma, mi) => ma << 8 | mi, registerDevice(dev, ops) {
      FS.devices[dev] = { stream_ops: ops };
    }, getDevice: (dev) => FS.devices[dev], getMounts(mount) {
      var mounts = [];
      var check = [mount];
      while (check.length) {
        var m = check.pop();
        mounts.push(m);
        check.push(...m.mounts);
      }
      return mounts;
    }, syncfs(populate, callback) {
      if (typeof populate == "function") {
        callback = populate;
        populate = false;
      }
      FS.syncFSRequests++;
      if (FS.syncFSRequests > 1) {
        err(`warning: ${FS.syncFSRequests} FS.syncfs operations in flight at once, probably just doing extra work`);
      }
      var mounts = FS.getMounts(FS.root.mount);
      var completed = 0;
      function doCallback(errCode) {
        FS.syncFSRequests--;
        return callback(errCode);
      }
      function done(errCode) {
        if (errCode) {
          if (!done.errored) {
            done.errored = true;
            return doCallback(errCode);
          }
          return;
        }
        if (++completed >= mounts.length) {
          doCallback(null);
        }
      }
      mounts.forEach((mount) => {
        if (!mount.type.syncfs) {
          return done(null);
        }
        mount.type.syncfs(mount, populate, done);
      });
    }, mount(type, opts, mountpoint) {
      var root = mountpoint === "/";
      var pseudo = !mountpoint;
      var node;
      if (root && FS.root) {
        throw new FS.ErrnoError(10);
      } else if (!root && !pseudo) {
        var lookup = FS.lookupPath(mountpoint, { follow_mount: false });
        mountpoint = lookup.path;
        node = lookup.node;
        if (FS.isMountpoint(node)) {
          throw new FS.ErrnoError(10);
        }
        if (!FS.isDir(node.mode)) {
          throw new FS.ErrnoError(54);
        }
      }
      var mount = { type, opts, mountpoint, mounts: [] };
      var mountRoot = type.mount(mount);
      mountRoot.mount = mount;
      mount.root = mountRoot;
      if (root) {
        FS.root = mountRoot;
      } else if (node) {
        node.mounted = mount;
        if (node.mount) {
          node.mount.mounts.push(mount);
        }
      }
      return mountRoot;
    }, unmount(mountpoint) {
      var lookup = FS.lookupPath(mountpoint, { follow_mount: false });
      if (!FS.isMountpoint(lookup.node)) {
        throw new FS.ErrnoError(28);
      }
      var node = lookup.node;
      var mount = node.mounted;
      var mounts = FS.getMounts(mount);
      Object.keys(FS.nameTable).forEach((hash) => {
        var current = FS.nameTable[hash];
        while (current) {
          var next = current.name_next;
          if (mounts.includes(current.mount)) {
            FS.destroyNode(current);
          }
          current = next;
        }
      });
      node.mounted = null;
      var idx = node.mount.mounts.indexOf(mount);
      node.mount.mounts.splice(idx, 1);
    }, lookup(parent, name) {
      return parent.node_ops.lookup(parent, name);
    }, mknod(path, mode, dev) {
      var lookup = FS.lookupPath(path, { parent: true });
      var parent = lookup.node;
      var name = PATH.basename(path);
      if (!name) {
        throw new FS.ErrnoError(28);
      }
      if (name === "." || name === "..") {
        throw new FS.ErrnoError(20);
      }
      var errCode = FS.mayCreate(parent, name);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      if (!parent.node_ops.mknod) {
        throw new FS.ErrnoError(63);
      }
      return parent.node_ops.mknod(parent, name, mode, dev);
    }, statfs(path) {
      return FS.statfsNode(FS.lookupPath(path, { follow: true }).node);
    }, statfsStream(stream) {
      return FS.statfsNode(stream.node);
    }, statfsNode(node) {
      var rtn = { bsize: 4096, frsize: 4096, blocks: 1e6, bfree: 5e5, bavail: 5e5, files: FS.nextInode, ffree: FS.nextInode - 1, fsid: 42, flags: 2, namelen: 255 };
      if (node.node_ops.statfs) {
        Object.assign(rtn, node.node_ops.statfs(node.mount.opts.root));
      }
      return rtn;
    }, create(path, mode = 438) {
      mode &= 4095;
      mode |= 32768;
      return FS.mknod(path, mode, 0);
    }, mkdir(path, mode = 511) {
      mode &= 511 | 512;
      mode |= 16384;
      return FS.mknod(path, mode, 0);
    }, mkdirTree(path, mode) {
      var dirs = path.split("/");
      var d = "";
      for (var dir of dirs) {
        if (!dir) continue;
        if (d || PATH.isAbs(path)) d += "/";
        d += dir;
        try {
          FS.mkdir(d, mode);
        } catch (e) {
          if (e.errno != 20) throw e;
        }
      }
    }, mkdev(path, mode, dev) {
      if (typeof dev == "undefined") {
        dev = mode;
        mode = 438;
      }
      mode |= 8192;
      return FS.mknod(path, mode, dev);
    }, symlink(oldpath, newpath) {
      if (!PATH_FS.resolve(oldpath)) {
        throw new FS.ErrnoError(44);
      }
      var lookup = FS.lookupPath(newpath, { parent: true });
      var parent = lookup.node;
      if (!parent) {
        throw new FS.ErrnoError(44);
      }
      var newname = PATH.basename(newpath);
      var errCode = FS.mayCreate(parent, newname);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      if (!parent.node_ops.symlink) {
        throw new FS.ErrnoError(63);
      }
      return parent.node_ops.symlink(parent, newname, oldpath);
    }, rename(old_path, new_path) {
      var old_dirname = PATH.dirname(old_path);
      var new_dirname = PATH.dirname(new_path);
      var old_name = PATH.basename(old_path);
      var new_name = PATH.basename(new_path);
      var lookup, old_dir, new_dir;
      lookup = FS.lookupPath(old_path, { parent: true });
      old_dir = lookup.node;
      lookup = FS.lookupPath(new_path, { parent: true });
      new_dir = lookup.node;
      if (!old_dir || !new_dir) throw new FS.ErrnoError(44);
      if (old_dir.mount !== new_dir.mount) {
        throw new FS.ErrnoError(75);
      }
      var old_node = FS.lookupNode(old_dir, old_name);
      var relative = PATH_FS.relative(old_path, new_dirname);
      if (relative.charAt(0) !== ".") {
        throw new FS.ErrnoError(28);
      }
      relative = PATH_FS.relative(new_path, old_dirname);
      if (relative.charAt(0) !== ".") {
        throw new FS.ErrnoError(55);
      }
      var new_node;
      try {
        new_node = FS.lookupNode(new_dir, new_name);
      } catch (e) {
      }
      if (old_node === new_node) {
        return;
      }
      var isdir = FS.isDir(old_node.mode);
      var errCode = FS.mayDelete(old_dir, old_name, isdir);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      errCode = new_node ? FS.mayDelete(new_dir, new_name, isdir) : FS.mayCreate(new_dir, new_name);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      if (!old_dir.node_ops.rename) {
        throw new FS.ErrnoError(63);
      }
      if (FS.isMountpoint(old_node) || new_node && FS.isMountpoint(new_node)) {
        throw new FS.ErrnoError(10);
      }
      if (new_dir !== old_dir) {
        errCode = FS.nodePermissions(old_dir, "w");
        if (errCode) {
          throw new FS.ErrnoError(errCode);
        }
      }
      FS.hashRemoveNode(old_node);
      try {
        old_dir.node_ops.rename(old_node, new_dir, new_name);
        old_node.parent = new_dir;
      } catch (e) {
        throw e;
      } finally {
        FS.hashAddNode(old_node);
      }
    }, rmdir(path) {
      var lookup = FS.lookupPath(path, { parent: true });
      var parent = lookup.node;
      var name = PATH.basename(path);
      var node = FS.lookupNode(parent, name);
      var errCode = FS.mayDelete(parent, name, true);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      if (!parent.node_ops.rmdir) {
        throw new FS.ErrnoError(63);
      }
      if (FS.isMountpoint(node)) {
        throw new FS.ErrnoError(10);
      }
      parent.node_ops.rmdir(parent, name);
      FS.destroyNode(node);
    }, readdir(path) {
      var lookup = FS.lookupPath(path, { follow: true });
      var node = lookup.node;
      var readdir = FS.checkOpExists(node.node_ops.readdir, 54);
      return readdir(node);
    }, unlink(path) {
      var lookup = FS.lookupPath(path, { parent: true });
      var parent = lookup.node;
      if (!parent) {
        throw new FS.ErrnoError(44);
      }
      var name = PATH.basename(path);
      var node = FS.lookupNode(parent, name);
      var errCode = FS.mayDelete(parent, name, false);
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      if (!parent.node_ops.unlink) {
        throw new FS.ErrnoError(63);
      }
      if (FS.isMountpoint(node)) {
        throw new FS.ErrnoError(10);
      }
      parent.node_ops.unlink(parent, name);
      FS.destroyNode(node);
    }, readlink(path) {
      var lookup = FS.lookupPath(path);
      var link = lookup.node;
      if (!link) {
        throw new FS.ErrnoError(44);
      }
      if (!link.node_ops.readlink) {
        throw new FS.ErrnoError(28);
      }
      return link.node_ops.readlink(link);
    }, stat(path, dontFollow) {
      var lookup = FS.lookupPath(path, { follow: !dontFollow });
      var node = lookup.node;
      var getattr = FS.checkOpExists(node.node_ops.getattr, 63);
      return getattr(node);
    }, fstat(fd) {
      var stream = FS.getStreamChecked(fd);
      var node = stream.node;
      var getattr = stream.stream_ops.getattr;
      var arg = getattr ? stream : node;
      getattr ??= node.node_ops.getattr;
      FS.checkOpExists(getattr, 63);
      return getattr(arg);
    }, lstat(path) {
      return FS.stat(path, true);
    }, doChmod(stream, node, mode, dontFollow) {
      FS.doSetAttr(stream, node, { mode: mode & 4095 | node.mode & ~4095, ctime: Date.now(), dontFollow });
    }, chmod(path, mode, dontFollow) {
      var node;
      if (typeof path == "string") {
        var lookup = FS.lookupPath(path, { follow: !dontFollow });
        node = lookup.node;
      } else {
        node = path;
      }
      FS.doChmod(null, node, mode, dontFollow);
    }, lchmod(path, mode) {
      FS.chmod(path, mode, true);
    }, fchmod(fd, mode) {
      var stream = FS.getStreamChecked(fd);
      FS.doChmod(stream, stream.node, mode, false);
    }, doChown(stream, node, dontFollow) {
      FS.doSetAttr(stream, node, { timestamp: Date.now(), dontFollow });
    }, chown(path, uid, gid, dontFollow) {
      var node;
      if (typeof path == "string") {
        var lookup = FS.lookupPath(path, { follow: !dontFollow });
        node = lookup.node;
      } else {
        node = path;
      }
      FS.doChown(null, node, dontFollow);
    }, lchown(path, uid, gid) {
      FS.chown(path, uid, gid, true);
    }, fchown(fd, uid, gid) {
      var stream = FS.getStreamChecked(fd);
      FS.doChown(stream, stream.node, false);
    }, doTruncate(stream, node, len) {
      if (FS.isDir(node.mode)) {
        throw new FS.ErrnoError(31);
      }
      if (!FS.isFile(node.mode)) {
        throw new FS.ErrnoError(28);
      }
      var errCode = FS.nodePermissions(node, "w");
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      FS.doSetAttr(stream, node, { size: len, timestamp: Date.now() });
    }, truncate(path, len) {
      if (len < 0) {
        throw new FS.ErrnoError(28);
      }
      var node;
      if (typeof path == "string") {
        var lookup = FS.lookupPath(path, { follow: true });
        node = lookup.node;
      } else {
        node = path;
      }
      FS.doTruncate(null, node, len);
    }, ftruncate(fd, len) {
      var stream = FS.getStreamChecked(fd);
      if (len < 0 || (stream.flags & 2097155) === 0) {
        throw new FS.ErrnoError(28);
      }
      FS.doTruncate(stream, stream.node, len);
    }, utime(path, atime, mtime) {
      var lookup = FS.lookupPath(path, { follow: true });
      var node = lookup.node;
      var setattr = FS.checkOpExists(node.node_ops.setattr, 63);
      setattr(node, { atime, mtime });
    }, open(path, flags, mode = 438) {
      if (path === "") {
        throw new FS.ErrnoError(44);
      }
      flags = typeof flags == "string" ? FS_modeStringToFlags(flags) : flags;
      if (flags & 64) {
        mode = mode & 4095 | 32768;
      } else {
        mode = 0;
      }
      var node;
      var isDirPath;
      if (typeof path == "object") {
        node = path;
      } else {
        isDirPath = path.endsWith("/");
        var lookup = FS.lookupPath(path, { follow: !(flags & 131072), noent_okay: true });
        node = lookup.node;
        path = lookup.path;
      }
      var created = false;
      if (flags & 64) {
        if (node) {
          if (flags & 128) {
            throw new FS.ErrnoError(20);
          }
        } else if (isDirPath) {
          throw new FS.ErrnoError(31);
        } else {
          node = FS.mknod(path, mode | 511, 0);
          created = true;
        }
      }
      if (!node) {
        throw new FS.ErrnoError(44);
      }
      if (FS.isChrdev(node.mode)) {
        flags &= ~512;
      }
      if (flags & 65536 && !FS.isDir(node.mode)) {
        throw new FS.ErrnoError(54);
      }
      if (!created) {
        var errCode = FS.mayOpen(node, flags);
        if (errCode) {
          throw new FS.ErrnoError(errCode);
        }
      }
      if (flags & 512 && !created) {
        FS.truncate(node, 0);
      }
      flags &= ~(128 | 512 | 131072);
      var stream = FS.createStream({ node, path: FS.getPath(node), flags, seekable: true, position: 0, stream_ops: node.stream_ops, ungotten: [], error: false });
      if (stream.stream_ops.open) {
        stream.stream_ops.open(stream);
      }
      if (created) {
        FS.chmod(node, mode & 511);
      }
      if (Module2["logReadFiles"] && !(flags & 1)) {
        if (!(path in FS.readFiles)) {
          FS.readFiles[path] = 1;
        }
      }
      return stream;
    }, close(stream) {
      if (FS.isClosed(stream)) {
        throw new FS.ErrnoError(8);
      }
      if (stream.getdents) stream.getdents = null;
      try {
        if (stream.stream_ops.close) {
          stream.stream_ops.close(stream);
        }
      } catch (e) {
        throw e;
      } finally {
        FS.closeStream(stream.fd);
      }
      stream.fd = null;
    }, isClosed(stream) {
      return stream.fd === null;
    }, llseek(stream, offset, whence) {
      if (FS.isClosed(stream)) {
        throw new FS.ErrnoError(8);
      }
      if (!stream.seekable || !stream.stream_ops.llseek) {
        throw new FS.ErrnoError(70);
      }
      if (whence != 0 && whence != 1 && whence != 2) {
        throw new FS.ErrnoError(28);
      }
      stream.position = stream.stream_ops.llseek(stream, offset, whence);
      stream.ungotten = [];
      return stream.position;
    }, read(stream, buffer, offset, length, position) {
      if (length < 0 || position < 0) {
        throw new FS.ErrnoError(28);
      }
      if (FS.isClosed(stream)) {
        throw new FS.ErrnoError(8);
      }
      if ((stream.flags & 2097155) === 1) {
        throw new FS.ErrnoError(8);
      }
      if (FS.isDir(stream.node.mode)) {
        throw new FS.ErrnoError(31);
      }
      if (!stream.stream_ops.read) {
        throw new FS.ErrnoError(28);
      }
      var seeking = typeof position != "undefined";
      if (!seeking) {
        position = stream.position;
      } else if (!stream.seekable) {
        throw new FS.ErrnoError(70);
      }
      var bytesRead = stream.stream_ops.read(stream, buffer, offset, length, position);
      if (!seeking) stream.position += bytesRead;
      return bytesRead;
    }, write(stream, buffer, offset, length, position, canOwn) {
      if (length < 0 || position < 0) {
        throw new FS.ErrnoError(28);
      }
      if (FS.isClosed(stream)) {
        throw new FS.ErrnoError(8);
      }
      if ((stream.flags & 2097155) === 0) {
        throw new FS.ErrnoError(8);
      }
      if (FS.isDir(stream.node.mode)) {
        throw new FS.ErrnoError(31);
      }
      if (!stream.stream_ops.write) {
        throw new FS.ErrnoError(28);
      }
      if (stream.seekable && stream.flags & 1024) {
        FS.llseek(stream, 0, 2);
      }
      var seeking = typeof position != "undefined";
      if (!seeking) {
        position = stream.position;
      } else if (!stream.seekable) {
        throw new FS.ErrnoError(70);
      }
      var bytesWritten = stream.stream_ops.write(stream, buffer, offset, length, position, canOwn);
      if (!seeking) stream.position += bytesWritten;
      return bytesWritten;
    }, mmap(stream, length, position, prot, flags) {
      if ((prot & 2) !== 0 && (flags & 2) === 0 && (stream.flags & 2097155) !== 2) {
        throw new FS.ErrnoError(2);
      }
      if ((stream.flags & 2097155) === 1) {
        throw new FS.ErrnoError(2);
      }
      if (!stream.stream_ops.mmap) {
        throw new FS.ErrnoError(43);
      }
      if (!length) {
        throw new FS.ErrnoError(28);
      }
      return stream.stream_ops.mmap(stream, length, position, prot, flags);
    }, msync(stream, buffer, offset, length, mmapFlags) {
      if (!stream.stream_ops.msync) {
        return 0;
      }
      return stream.stream_ops.msync(stream, buffer, offset, length, mmapFlags);
    }, ioctl(stream, cmd, arg) {
      if (!stream.stream_ops.ioctl) {
        throw new FS.ErrnoError(59);
      }
      return stream.stream_ops.ioctl(stream, cmd, arg);
    }, readFile(path, opts = {}) {
      opts.flags = opts.flags || 0;
      opts.encoding = opts.encoding || "binary";
      if (opts.encoding !== "utf8" && opts.encoding !== "binary") {
        throw new Error(`Invalid encoding type "${opts.encoding}"`);
      }
      var ret;
      var stream = FS.open(path, opts.flags);
      var stat = FS.stat(path);
      var length = stat.size;
      var buf = new Uint8Array(length);
      FS.read(stream, buf, 0, length, 0);
      if (opts.encoding === "utf8") {
        ret = UTF8ArrayToString(buf);
      } else if (opts.encoding === "binary") {
        ret = buf;
      }
      FS.close(stream);
      return ret;
    }, writeFile(path, data, opts = {}) {
      opts.flags = opts.flags || 577;
      var stream = FS.open(path, opts.flags, opts.mode);
      if (typeof data == "string") {
        var buf = new Uint8Array(lengthBytesUTF8(data) + 1);
        var actualNumBytes = stringToUTF8Array(data, buf, 0, buf.length);
        FS.write(stream, buf, 0, actualNumBytes, void 0, opts.canOwn);
      } else if (ArrayBuffer.isView(data)) {
        FS.write(stream, data, 0, data.byteLength, void 0, opts.canOwn);
      } else {
        throw new Error("Unsupported data type");
      }
      FS.close(stream);
    }, cwd: () => FS.currentPath, chdir(path) {
      var lookup = FS.lookupPath(path, { follow: true });
      if (lookup.node === null) {
        throw new FS.ErrnoError(44);
      }
      if (!FS.isDir(lookup.node.mode)) {
        throw new FS.ErrnoError(54);
      }
      var errCode = FS.nodePermissions(lookup.node, "x");
      if (errCode) {
        throw new FS.ErrnoError(errCode);
      }
      FS.currentPath = lookup.path;
    }, createDefaultDirectories() {
      FS.mkdir("/tmp");
      FS.mkdir("/home");
      FS.mkdir("/home/web_user");
    }, createDefaultDevices() {
      FS.mkdir("/dev");
      FS.registerDevice(FS.makedev(1, 3), { read: () => 0, write: (stream, buffer, offset, length, pos) => length, llseek: () => 0 });
      FS.mkdev("/dev/null", FS.makedev(1, 3));
      TTY.register(FS.makedev(5, 0), TTY.default_tty_ops);
      TTY.register(FS.makedev(6, 0), TTY.default_tty1_ops);
      FS.mkdev("/dev/tty", FS.makedev(5, 0));
      FS.mkdev("/dev/tty1", FS.makedev(6, 0));
      var randomBuffer = new Uint8Array(1024), randomLeft = 0;
      var randomByte = () => {
        if (randomLeft === 0) {
          randomFill(randomBuffer);
          randomLeft = randomBuffer.byteLength;
        }
        return randomBuffer[--randomLeft];
      };
      FS.createDevice("/dev", "random", randomByte);
      FS.createDevice("/dev", "urandom", randomByte);
      FS.mkdir("/dev/shm");
      FS.mkdir("/dev/shm/tmp");
    }, createSpecialDirectories() {
      FS.mkdir("/proc");
      var proc_self = FS.mkdir("/proc/self");
      FS.mkdir("/proc/self/fd");
      FS.mount({ mount() {
        var node = FS.createNode(proc_self, "fd", 16895, 73);
        node.stream_ops = { llseek: MEMFS.stream_ops.llseek };
        node.node_ops = { lookup(parent, name) {
          var fd = +name;
          var stream = FS.getStreamChecked(fd);
          var ret = { parent: null, mount: { mountpoint: "fake" }, node_ops: { readlink: () => stream.path }, id: fd + 1 };
          ret.parent = ret;
          return ret;
        }, readdir() {
          return Array.from(FS.streams.entries()).filter(([k, v]) => v).map(([k, v]) => k.toString());
        } };
        return node;
      } }, {}, "/proc/self/fd");
    }, createStandardStreams(input, output, error) {
      if (input) {
        FS.createDevice("/dev", "stdin", input);
      } else {
        FS.symlink("/dev/tty", "/dev/stdin");
      }
      if (output) {
        FS.createDevice("/dev", "stdout", null, output);
      } else {
        FS.symlink("/dev/tty", "/dev/stdout");
      }
      if (error) {
        FS.createDevice("/dev", "stderr", null, error);
      } else {
        FS.symlink("/dev/tty1", "/dev/stderr");
      }
      var stdin = FS.open("/dev/stdin", 0);
      var stdout = FS.open("/dev/stdout", 1);
      var stderr = FS.open("/dev/stderr", 1);
    }, staticInit() {
      FS.nameTable = new Array(4096);
      FS.mount(MEMFS, {}, "/");
      FS.createDefaultDirectories();
      FS.createDefaultDevices();
      FS.createSpecialDirectories();
      FS.filesystems = { MEMFS };
    }, init(input, output, error) {
      FS.initialized = true;
      input ??= Module2["stdin"];
      output ??= Module2["stdout"];
      error ??= Module2["stderr"];
      FS.createStandardStreams(input, output, error);
    }, quit() {
      FS.initialized = false;
      for (var stream of FS.streams) {
        if (stream) {
          FS.close(stream);
        }
      }
    }, findObject(path, dontResolveLastLink) {
      var ret = FS.analyzePath(path, dontResolveLastLink);
      if (!ret.exists) {
        return null;
      }
      return ret.object;
    }, analyzePath(path, dontResolveLastLink) {
      try {
        var lookup = FS.lookupPath(path, { follow: !dontResolveLastLink });
        path = lookup.path;
      } catch (e) {
      }
      var ret = { isRoot: false, exists: false, error: 0, name: null, path: null, object: null, parentExists: false, parentPath: null, parentObject: null };
      try {
        var lookup = FS.lookupPath(path, { parent: true });
        ret.parentExists = true;
        ret.parentPath = lookup.path;
        ret.parentObject = lookup.node;
        ret.name = PATH.basename(path);
        lookup = FS.lookupPath(path, { follow: !dontResolveLastLink });
        ret.exists = true;
        ret.path = lookup.path;
        ret.object = lookup.node;
        ret.name = lookup.node.name;
        ret.isRoot = lookup.path === "/";
      } catch (e) {
        ret.error = e.errno;
      }
      return ret;
    }, createPath(parent, path, canRead, canWrite) {
      parent = typeof parent == "string" ? parent : FS.getPath(parent);
      var parts = path.split("/").reverse();
      while (parts.length) {
        var part = parts.pop();
        if (!part) continue;
        var current = PATH.join2(parent, part);
        try {
          FS.mkdir(current);
        } catch (e) {
          if (e.errno != 20) throw e;
        }
        parent = current;
      }
      return current;
    }, createFile(parent, name, properties, canRead, canWrite) {
      var path = PATH.join2(typeof parent == "string" ? parent : FS.getPath(parent), name);
      var mode = FS_getMode(canRead, canWrite);
      return FS.create(path, mode);
    }, createDataFile(parent, name, data, canRead, canWrite, canOwn) {
      var path = name;
      if (parent) {
        parent = typeof parent == "string" ? parent : FS.getPath(parent);
        path = name ? PATH.join2(parent, name) : parent;
      }
      var mode = FS_getMode(canRead, canWrite);
      var node = FS.create(path, mode);
      if (data) {
        if (typeof data == "string") {
          var arr = new Array(data.length);
          for (var i = 0, len = data.length; i < len; ++i) arr[i] = data.charCodeAt(i);
          data = arr;
        }
        FS.chmod(node, mode | 146);
        var stream = FS.open(node, 577);
        FS.write(stream, data, 0, data.length, 0, canOwn);
        FS.close(stream);
        FS.chmod(node, mode);
      }
    }, createDevice(parent, name, input, output) {
      var path = PATH.join2(typeof parent == "string" ? parent : FS.getPath(parent), name);
      var mode = FS_getMode(!!input, !!output);
      FS.createDevice.major ??= 64;
      var dev = FS.makedev(FS.createDevice.major++, 0);
      FS.registerDevice(dev, { open(stream) {
        stream.seekable = false;
      }, close(stream) {
        if (output?.buffer?.length) {
          output(10);
        }
      }, read(stream, buffer, offset, length, pos) {
        var bytesRead = 0;
        for (var i = 0; i < length; i++) {
          var result;
          try {
            result = input();
          } catch (e) {
            throw new FS.ErrnoError(29);
          }
          if (result === void 0 && bytesRead === 0) {
            throw new FS.ErrnoError(6);
          }
          if (result === null || result === void 0) break;
          bytesRead++;
          buffer[offset + i] = result;
        }
        if (bytesRead) {
          stream.node.atime = Date.now();
        }
        return bytesRead;
      }, write(stream, buffer, offset, length, pos) {
        for (var i = 0; i < length; i++) {
          try {
            output(buffer[offset + i]);
          } catch (e) {
            throw new FS.ErrnoError(29);
          }
        }
        if (length) {
          stream.node.mtime = stream.node.ctime = Date.now();
        }
        return i;
      } });
      return FS.mkdev(path, mode, dev);
    }, forceLoadFile(obj) {
      if (obj.isDevice || obj.isFolder || obj.link || obj.contents) return true;
      if (typeof XMLHttpRequest != "undefined") {
        throw new Error("Lazy loading should have been performed (contents set) in createLazyFile, but it was not. Lazy loading only works in web workers. Use --embed-file or --preload-file in emcc on the main thread.");
      } else {
        try {
          obj.contents = readBinary(obj.url);
          obj.usedBytes = obj.contents.length;
        } catch (e) {
          throw new FS.ErrnoError(29);
        }
      }
    }, createLazyFile(parent, name, url, canRead, canWrite) {
      class LazyUint8Array {
        lengthKnown = false;
        chunks = [];
        get(idx) {
          if (idx > this.length - 1 || idx < 0) {
            return void 0;
          }
          var chunkOffset = idx % this.chunkSize;
          var chunkNum = idx / this.chunkSize | 0;
          return this.getter(chunkNum)[chunkOffset];
        }
        setDataGetter(getter) {
          this.getter = getter;
        }
        cacheLength() {
          var xhr = new XMLHttpRequest();
          xhr.open("HEAD", url, false);
          xhr.send(null);
          if (!(xhr.status >= 200 && xhr.status < 300 || xhr.status === 304)) throw new Error("Couldn't load " + url + ". Status: " + xhr.status);
          var datalength = Number(xhr.getResponseHeader("Content-length"));
          var header;
          var hasByteServing = (header = xhr.getResponseHeader("Accept-Ranges")) && header === "bytes";
          var usesGzip = (header = xhr.getResponseHeader("Content-Encoding")) && header === "gzip";
          var chunkSize = 1024 * 1024;
          if (!hasByteServing) chunkSize = datalength;
          var doXHR = (from, to) => {
            if (from > to) throw new Error("invalid range (" + from + ", " + to + ") or no bytes requested!");
            if (to > datalength - 1) throw new Error("only " + datalength + " bytes available! programmer error!");
            var xhr2 = new XMLHttpRequest();
            xhr2.open("GET", url, false);
            if (datalength !== chunkSize) xhr2.setRequestHeader("Range", "bytes=" + from + "-" + to);
            xhr2.responseType = "arraybuffer";
            if (xhr2.overrideMimeType) {
              xhr2.overrideMimeType("text/plain; charset=x-user-defined");
            }
            xhr2.send(null);
            if (!(xhr2.status >= 200 && xhr2.status < 300 || xhr2.status === 304)) throw new Error("Couldn't load " + url + ". Status: " + xhr2.status);
            if (xhr2.response !== void 0) {
              return new Uint8Array(xhr2.response || []);
            }
            return intArrayFromString(xhr2.responseText || "", true);
          };
          var lazyArray2 = this;
          lazyArray2.setDataGetter((chunkNum) => {
            var start = chunkNum * chunkSize;
            var end = (chunkNum + 1) * chunkSize - 1;
            end = Math.min(end, datalength - 1);
            if (typeof lazyArray2.chunks[chunkNum] == "undefined") {
              lazyArray2.chunks[chunkNum] = doXHR(start, end);
            }
            if (typeof lazyArray2.chunks[chunkNum] == "undefined") throw new Error("doXHR failed!");
            return lazyArray2.chunks[chunkNum];
          });
          if (usesGzip || !datalength) {
            chunkSize = datalength = 1;
            datalength = this.getter(0).length;
            chunkSize = datalength;
            out("LazyFiles on gzip forces download of the whole file when length is accessed");
          }
          this._length = datalength;
          this._chunkSize = chunkSize;
          this.lengthKnown = true;
        }
        get length() {
          if (!this.lengthKnown) {
            this.cacheLength();
          }
          return this._length;
        }
        get chunkSize() {
          if (!this.lengthKnown) {
            this.cacheLength();
          }
          return this._chunkSize;
        }
      }
      if (typeof XMLHttpRequest != "undefined") {
        if (!ENVIRONMENT_IS_WORKER) throw "Cannot do synchronous binary XHRs outside webworkers in modern browsers. Use --embed-file or --preload-file in emcc";
        var lazyArray = new LazyUint8Array();
        var properties = { isDevice: false, contents: lazyArray };
      } else {
        var properties = { isDevice: false, url };
      }
      var node = FS.createFile(parent, name, properties, canRead, canWrite);
      if (properties.contents) {
        node.contents = properties.contents;
      } else if (properties.url) {
        node.contents = null;
        node.url = properties.url;
      }
      Object.defineProperties(node, { usedBytes: { get: function() {
        return this.contents.length;
      } } });
      var stream_ops = {};
      var keys = Object.keys(node.stream_ops);
      keys.forEach((key) => {
        var fn = node.stream_ops[key];
        stream_ops[key] = (...args) => {
          FS.forceLoadFile(node);
          return fn(...args);
        };
      });
      function writeChunks(stream, buffer, offset, length, position) {
        var contents = stream.node.contents;
        if (position >= contents.length) return 0;
        var size = Math.min(contents.length - position, length);
        if (contents.slice) {
          for (var i = 0; i < size; i++) {
            buffer[offset + i] = contents[position + i];
          }
        } else {
          for (var i = 0; i < size; i++) {
            buffer[offset + i] = contents.get(position + i);
          }
        }
        return size;
      }
      stream_ops.read = (stream, buffer, offset, length, position) => {
        FS.forceLoadFile(node);
        return writeChunks(stream, buffer, offset, length, position);
      };
      stream_ops.mmap = (stream, length, position, prot, flags) => {
        FS.forceLoadFile(node);
        var ptr2 = mmapAlloc(length);
        if (!ptr2) {
          throw new FS.ErrnoError(48);
        }
        writeChunks(stream, HEAP8, ptr2, length, position);
        return { ptr: ptr2, allocated: true };
      };
      node.stream_ops = stream_ops;
      return node;
    } };
    var UTF8ToString = (ptr2, maxBytesToRead) => ptr2 ? UTF8ArrayToString(HEAPU8, ptr2, maxBytesToRead) : "";
    var SYSCALLS = { DEFAULT_POLLMASK: 5, calculateAt(dirfd, path, allowEmpty) {
      if (PATH.isAbs(path)) {
        return path;
      }
      var dir;
      if (dirfd === -100) {
        dir = FS.cwd();
      } else {
        var dirstream = SYSCALLS.getStreamFromFD(dirfd);
        dir = dirstream.path;
      }
      if (path.length == 0) {
        if (!allowEmpty) {
          throw new FS.ErrnoError(44);
        }
        return dir;
      }
      return dir + "/" + path;
    }, writeStat(buf, stat) {
      HEAP32[buf >> 2] = stat.dev;
      HEAP32[buf + 4 >> 2] = stat.mode;
      HEAPU32[buf + 8 >> 2] = stat.nlink;
      HEAP32[buf + 12 >> 2] = stat.uid;
      HEAP32[buf + 16 >> 2] = stat.gid;
      HEAP32[buf + 20 >> 2] = stat.rdev;
      HEAP64[buf + 24 >> 3] = BigInt(stat.size);
      HEAP32[buf + 32 >> 2] = 4096;
      HEAP32[buf + 36 >> 2] = stat.blocks;
      var atime = stat.atime.getTime();
      var mtime = stat.mtime.getTime();
      var ctime = stat.ctime.getTime();
      HEAP64[buf + 40 >> 3] = BigInt(Math.floor(atime / 1e3));
      HEAPU32[buf + 48 >> 2] = atime % 1e3 * 1e3 * 1e3;
      HEAP64[buf + 56 >> 3] = BigInt(Math.floor(mtime / 1e3));
      HEAPU32[buf + 64 >> 2] = mtime % 1e3 * 1e3 * 1e3;
      HEAP64[buf + 72 >> 3] = BigInt(Math.floor(ctime / 1e3));
      HEAPU32[buf + 80 >> 2] = ctime % 1e3 * 1e3 * 1e3;
      HEAP64[buf + 88 >> 3] = BigInt(stat.ino);
      return 0;
    }, writeStatFs(buf, stats) {
      HEAP32[buf + 4 >> 2] = stats.bsize;
      HEAP32[buf + 40 >> 2] = stats.bsize;
      HEAP32[buf + 8 >> 2] = stats.blocks;
      HEAP32[buf + 12 >> 2] = stats.bfree;
      HEAP32[buf + 16 >> 2] = stats.bavail;
      HEAP32[buf + 20 >> 2] = stats.files;
      HEAP32[buf + 24 >> 2] = stats.ffree;
      HEAP32[buf + 28 >> 2] = stats.fsid;
      HEAP32[buf + 44 >> 2] = stats.flags;
      HEAP32[buf + 36 >> 2] = stats.namelen;
    }, doMsync(addr, stream, len, flags, offset) {
      if (!FS.isFile(stream.node.mode)) {
        throw new FS.ErrnoError(43);
      }
      if (flags & 2) {
        return 0;
      }
      var buffer = HEAPU8.slice(addr, addr + len);
      FS.msync(stream, buffer, offset, len, flags);
    }, getStreamFromFD(fd) {
      var stream = FS.getStreamChecked(fd);
      return stream;
    }, varargs: void 0, getStr(ptr2) {
      var ret = UTF8ToString(ptr2);
      return ret;
    } };
    function ___syscall_fcntl64(fd, cmd, varargs) {
      SYSCALLS.varargs = varargs;
      try {
        var stream = SYSCALLS.getStreamFromFD(fd);
        switch (cmd) {
          case 0: {
            var arg = syscallGetVarargI();
            if (arg < 0) {
              return -28;
            }
            while (FS.streams[arg]) {
              arg++;
            }
            var newStream;
            newStream = FS.dupStream(stream, arg);
            return newStream.fd;
          }
          case 1:
          case 2:
            return 0;
          case 3:
            return stream.flags;
          case 4: {
            var arg = syscallGetVarargI();
            stream.flags |= arg;
            return 0;
          }
          case 12: {
            var arg = syscallGetVarargP();
            var offset = 0;
            HEAP16[arg + offset >> 1] = 2;
            return 0;
          }
          case 13:
          case 14:
            return 0;
        }
        return -28;
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return -e.errno;
      }
    }
    function ___syscall_ioctl(fd, op, varargs) {
      SYSCALLS.varargs = varargs;
      try {
        var stream = SYSCALLS.getStreamFromFD(fd);
        switch (op) {
          case 21509: {
            if (!stream.tty) return -59;
            return 0;
          }
          case 21505: {
            if (!stream.tty) return -59;
            if (stream.tty.ops.ioctl_tcgets) {
              var termios = stream.tty.ops.ioctl_tcgets(stream);
              var argp = syscallGetVarargP();
              HEAP32[argp >> 2] = termios.c_iflag || 0;
              HEAP32[argp + 4 >> 2] = termios.c_oflag || 0;
              HEAP32[argp + 8 >> 2] = termios.c_cflag || 0;
              HEAP32[argp + 12 >> 2] = termios.c_lflag || 0;
              for (var i = 0; i < 32; i++) {
                HEAP8[argp + i + 17] = termios.c_cc[i] || 0;
              }
              return 0;
            }
            return 0;
          }
          case 21510:
          case 21511:
          case 21512: {
            if (!stream.tty) return -59;
            return 0;
          }
          case 21506:
          case 21507:
          case 21508: {
            if (!stream.tty) return -59;
            if (stream.tty.ops.ioctl_tcsets) {
              var argp = syscallGetVarargP();
              var c_iflag = HEAP32[argp >> 2];
              var c_oflag = HEAP32[argp + 4 >> 2];
              var c_cflag = HEAP32[argp + 8 >> 2];
              var c_lflag = HEAP32[argp + 12 >> 2];
              var c_cc = [];
              for (var i = 0; i < 32; i++) {
                c_cc.push(HEAP8[argp + i + 17]);
              }
              return stream.tty.ops.ioctl_tcsets(stream.tty, op, { c_iflag, c_oflag, c_cflag, c_lflag, c_cc });
            }
            return 0;
          }
          case 21519: {
            if (!stream.tty) return -59;
            var argp = syscallGetVarargP();
            HEAP32[argp >> 2] = 0;
            return 0;
          }
          case 21520: {
            if (!stream.tty) return -59;
            return -28;
          }
          case 21531: {
            var argp = syscallGetVarargP();
            return FS.ioctl(stream, op, argp);
          }
          case 21523: {
            if (!stream.tty) return -59;
            if (stream.tty.ops.ioctl_tiocgwinsz) {
              var winsize = stream.tty.ops.ioctl_tiocgwinsz(stream.tty);
              var argp = syscallGetVarargP();
              HEAP16[argp >> 1] = winsize[0];
              HEAP16[argp + 2 >> 1] = winsize[1];
            }
            return 0;
          }
          case 21524: {
            if (!stream.tty) return -59;
            return 0;
          }
          case 21515: {
            if (!stream.tty) return -59;
            return 0;
          }
          default:
            return -28;
        }
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return -e.errno;
      }
    }
    function ___syscall_openat(dirfd, path, flags, varargs) {
      SYSCALLS.varargs = varargs;
      try {
        path = SYSCALLS.getStr(path);
        path = SYSCALLS.calculateAt(dirfd, path);
        var mode = varargs ? syscallGetVarargI() : 0;
        return FS.open(path, flags, mode).fd;
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return -e.errno;
      }
    }
    var __abort_js = () => abort("");
    var isLeapYear = (year) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    var MONTH_DAYS_LEAP_CUMULATIVE = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
    var MONTH_DAYS_REGULAR_CUMULATIVE = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    var ydayFromDate = (date) => {
      var leap = isLeapYear(date.getFullYear());
      var monthDaysCumulative = leap ? MONTH_DAYS_LEAP_CUMULATIVE : MONTH_DAYS_REGULAR_CUMULATIVE;
      var yday = monthDaysCumulative[date.getMonth()] + date.getDate() - 1;
      return yday;
    };
    var INT53_MAX = 9007199254740992;
    var INT53_MIN = -9007199254740992;
    var bigintToI53Checked = (num) => num < INT53_MIN || num > INT53_MAX ? NaN : Number(num);
    function __localtime_js(time, tmPtr) {
      time = bigintToI53Checked(time);
      var date = new Date(time * 1e3);
      HEAP32[tmPtr >> 2] = date.getSeconds();
      HEAP32[tmPtr + 4 >> 2] = date.getMinutes();
      HEAP32[tmPtr + 8 >> 2] = date.getHours();
      HEAP32[tmPtr + 12 >> 2] = date.getDate();
      HEAP32[tmPtr + 16 >> 2] = date.getMonth();
      HEAP32[tmPtr + 20 >> 2] = date.getFullYear() - 1900;
      HEAP32[tmPtr + 24 >> 2] = date.getDay();
      var yday = ydayFromDate(date) | 0;
      HEAP32[tmPtr + 28 >> 2] = yday;
      HEAP32[tmPtr + 36 >> 2] = -(date.getTimezoneOffset() * 60);
      var start = new Date(date.getFullYear(), 0, 1);
      var summerOffset = new Date(date.getFullYear(), 6, 1).getTimezoneOffset();
      var winterOffset = start.getTimezoneOffset();
      var dst = (summerOffset != winterOffset && date.getTimezoneOffset() == Math.min(winterOffset, summerOffset)) | 0;
      HEAP32[tmPtr + 32 >> 2] = dst;
    }
    var __mktime_js = function(tmPtr) {
      var ret = (() => {
        var date = new Date(HEAP32[tmPtr + 20 >> 2] + 1900, HEAP32[tmPtr + 16 >> 2], HEAP32[tmPtr + 12 >> 2], HEAP32[tmPtr + 8 >> 2], HEAP32[tmPtr + 4 >> 2], HEAP32[tmPtr >> 2], 0);
        var dst = HEAP32[tmPtr + 32 >> 2];
        var guessedOffset = date.getTimezoneOffset();
        var start = new Date(date.getFullYear(), 0, 1);
        var summerOffset = new Date(date.getFullYear(), 6, 1).getTimezoneOffset();
        var winterOffset = start.getTimezoneOffset();
        var dstOffset = Math.min(winterOffset, summerOffset);
        if (dst < 0) {
          HEAP32[tmPtr + 32 >> 2] = Number(summerOffset != winterOffset && dstOffset == guessedOffset);
        } else if (dst > 0 != (dstOffset == guessedOffset)) {
          var nonDstOffset = Math.max(winterOffset, summerOffset);
          var trueOffset = dst > 0 ? dstOffset : nonDstOffset;
          date.setTime(date.getTime() + (trueOffset - guessedOffset) * 6e4);
        }
        HEAP32[tmPtr + 24 >> 2] = date.getDay();
        var yday = ydayFromDate(date) | 0;
        HEAP32[tmPtr + 28 >> 2] = yday;
        HEAP32[tmPtr >> 2] = date.getSeconds();
        HEAP32[tmPtr + 4 >> 2] = date.getMinutes();
        HEAP32[tmPtr + 8 >> 2] = date.getHours();
        HEAP32[tmPtr + 12 >> 2] = date.getDate();
        HEAP32[tmPtr + 16 >> 2] = date.getMonth();
        HEAP32[tmPtr + 20 >> 2] = date.getYear();
        var timeMs = date.getTime();
        if (isNaN(timeMs)) {
          return -1;
        }
        return timeMs / 1e3;
      })();
      return BigInt(ret);
    };
    var stringToUTF8 = (str, outPtr, maxBytesToWrite) => stringToUTF8Array(str, HEAPU8, outPtr, maxBytesToWrite);
    var __tzset_js = (timezone, daylight, std_name, dst_name) => {
      var currentYear = (/* @__PURE__ */ new Date()).getFullYear();
      var winter = new Date(currentYear, 0, 1);
      var summer = new Date(currentYear, 6, 1);
      var winterOffset = winter.getTimezoneOffset();
      var summerOffset = summer.getTimezoneOffset();
      var stdTimezoneOffset = Math.max(winterOffset, summerOffset);
      HEAPU32[timezone >> 2] = stdTimezoneOffset * 60;
      HEAP32[daylight >> 2] = Number(winterOffset != summerOffset);
      var extractZone = (timezoneOffset) => {
        var sign = timezoneOffset >= 0 ? "-" : "+";
        var absOffset = Math.abs(timezoneOffset);
        var hours = String(Math.floor(absOffset / 60)).padStart(2, "0");
        var minutes = String(absOffset % 60).padStart(2, "0");
        return `UTC${sign}${hours}${minutes}`;
      };
      var winterName = extractZone(winterOffset);
      var summerName = extractZone(summerOffset);
      if (summerOffset < winterOffset) {
        stringToUTF8(winterName, std_name, 17);
        stringToUTF8(summerName, dst_name, 17);
      } else {
        stringToUTF8(winterName, dst_name, 17);
        stringToUTF8(summerName, std_name, 17);
      }
    };
    var getHeapMax = () => 2147483648;
    var alignMemory = (size, alignment) => Math.ceil(size / alignment) * alignment;
    var growMemory = (size) => {
      var b = wasmMemory.buffer;
      var pages = (size - b.byteLength + 65535) / 65536 | 0;
      try {
        wasmMemory.grow(pages);
        updateMemoryViews();
        return 1;
      } catch (e) {
      }
    };
    var _emscripten_resize_heap = (requestedSize) => {
      var oldSize = HEAPU8.length;
      requestedSize >>>= 0;
      var maxHeapSize = getHeapMax();
      if (requestedSize > maxHeapSize) {
        return false;
      }
      for (var cutDown = 1; cutDown <= 4; cutDown *= 2) {
        var overGrownHeapSize = oldSize * (1 + 0.2 / cutDown);
        overGrownHeapSize = Math.min(overGrownHeapSize, requestedSize + 100663296);
        var newSize = Math.min(maxHeapSize, alignMemory(Math.max(requestedSize, overGrownHeapSize), 65536));
        var replacement = growMemory(newSize);
        if (replacement) {
          return true;
        }
      }
      return false;
    };
    function _fd_close(fd) {
      try {
        var stream = SYSCALLS.getStreamFromFD(fd);
        FS.close(stream);
        return 0;
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return e.errno;
      }
    }
    var doReadv = (stream, iov, iovcnt, offset) => {
      var ret = 0;
      for (var i = 0; i < iovcnt; i++) {
        var ptr2 = HEAPU32[iov >> 2];
        var len = HEAPU32[iov + 4 >> 2];
        iov += 8;
        var curr = FS.read(stream, HEAP8, ptr2, len, offset);
        if (curr < 0) return -1;
        ret += curr;
        if (curr < len) break;
        if (typeof offset != "undefined") {
          offset += curr;
        }
      }
      return ret;
    };
    function _fd_read(fd, iov, iovcnt, pnum) {
      try {
        var stream = SYSCALLS.getStreamFromFD(fd);
        var num = doReadv(stream, iov, iovcnt);
        HEAPU32[pnum >> 2] = num;
        return 0;
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return e.errno;
      }
    }
    function _fd_seek(fd, offset, whence, newOffset) {
      offset = bigintToI53Checked(offset);
      try {
        if (isNaN(offset)) return 61;
        var stream = SYSCALLS.getStreamFromFD(fd);
        FS.llseek(stream, offset, whence);
        HEAP64[newOffset >> 3] = BigInt(stream.position);
        if (stream.getdents && offset === 0 && whence === 0) stream.getdents = null;
        return 0;
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return e.errno;
      }
    }
    var doWritev = (stream, iov, iovcnt, offset) => {
      var ret = 0;
      for (var i = 0; i < iovcnt; i++) {
        var ptr2 = HEAPU32[iov >> 2];
        var len = HEAPU32[iov + 4 >> 2];
        iov += 8;
        var curr = FS.write(stream, HEAP8, ptr2, len, offset);
        if (curr < 0) return -1;
        ret += curr;
        if (curr < len) {
          break;
        }
        if (typeof offset != "undefined") {
          offset += curr;
        }
      }
      return ret;
    };
    function _fd_write(fd, iov, iovcnt, pnum) {
      try {
        var stream = SYSCALLS.getStreamFromFD(fd);
        var num = doWritev(stream, iov, iovcnt);
        HEAPU32[pnum >> 2] = num;
        return 0;
      } catch (e) {
        if (typeof FS == "undefined" || !(e.name === "ErrnoError")) throw e;
        return e.errno;
      }
    }
    var _llvm_eh_typeid_for = (type) => type;
    var wasmTable;
    var getWasmTableEntry = (funcPtr) => wasmTable.get(funcPtr);
    FS.createPreloadedFile = FS_createPreloadedFile;
    FS.staticInit();
    MEMFS.doesNotExistError = new FS.ErrnoError(44);
    MEMFS.doesNotExistError.stack = "<generic error, no stack>";
    {
      if (Module2["noExitRuntime"]) noExitRuntime = Module2["noExitRuntime"];
      if (Module2["preloadPlugins"]) preloadPlugins = Module2["preloadPlugins"];
      if (Module2["print"]) out = Module2["print"];
      if (Module2["printErr"]) err = Module2["printErr"];
      if (Module2["wasmBinary"]) wasmBinary = Module2["wasmBinary"];
      if (Module2["arguments"]) arguments_ = Module2["arguments"];
      if (Module2["thisProgram"]) thisProgram = Module2["thisProgram"];
    }
    var wasmImports = { j: ___cxa_begin_catch, m: ___cxa_end_catch, e: ___cxa_find_matching_catch_2, f: ___cxa_find_matching_catch_3, z: ___cxa_find_matching_catch_4, A: ___cxa_find_matching_catch_5, Q: ___cxa_rethrow, d: ___cxa_throw, h: ___resumeException, x: ___syscall_fcntl64, J: ___syscall_ioctl, K: ___syscall_openat, C: __abort_js, E: __localtime_js, F: __mktime_js, G: __tzset_js, D: _emscripten_resize_heap, v: _fd_close, I: _fd_read, H: _fd_seek, w: _fd_write, o: invoke_dii, s: invoke_diii, a: invoke_ii, b: invoke_iii, l: invoke_iiii, g: invoke_iiiii, O: invoke_iiiiiii, y: invoke_iiiiiiiii, P: invoke_iiiijjii, n: invoke_iiji, q: invoke_ji, k: invoke_v, c: invoke_vi, L: invoke_viff, M: invoke_vifff, r: invoke_vii, i: invoke_viii, t: invoke_viiii, B: invoke_viiiii, N: invoke_viiiiii, u: invoke_viiijii, p: _llvm_eh_typeid_for };
    var wasmExports = await createWasm();
    var ___wasm_call_ctors = wasmExports["S"];
    var _libraw_init = Module2["_libraw_init"] = wasmExports["U"];
    var _libraw_version = Module2["_libraw_version"] = wasmExports["V"];
    var _libraw_strprogress = Module2["_libraw_strprogress"] = wasmExports["W"];
    var _libraw_versionNumber = Module2["_libraw_versionNumber"] = wasmExports["X"];
    var _libraw_cameraList = Module2["_libraw_cameraList"] = wasmExports["Y"];
    var _libraw_cameraCount = Module2["_libraw_cameraCount"] = wasmExports["Z"];
    var _libraw_unpack_function_name = Module2["_libraw_unpack_function_name"] = wasmExports["_"];
    var _libraw_subtract_black = Module2["_libraw_subtract_black"] = wasmExports["$"];
    var _libraw_get_iparams = Module2["_libraw_get_iparams"] = wasmExports["aa"];
    var _libraw_get_lensinfo = Module2["_libraw_get_lensinfo"] = wasmExports["ba"];
    var _libraw_get_imgother = Module2["_libraw_get_imgother"] = wasmExports["ca"];
    var _libraw_open_buffer = Module2["_libraw_open_buffer"] = wasmExports["da"];
    var _libraw_unpack = Module2["_libraw_unpack"] = wasmExports["ea"];
    var _libraw_unpack_thumb = Module2["_libraw_unpack_thumb"] = wasmExports["fa"];
    var _libraw_unpack_thumb_ex = Module2["_libraw_unpack_thumb_ex"] = wasmExports["ga"];
    var _libraw_recycle = Module2["_libraw_recycle"] = wasmExports["ha"];
    var _libraw_close = Module2["_libraw_close"] = wasmExports["ia"];
    var _libraw_dcraw_process = Module2["_libraw_dcraw_process"] = wasmExports["ja"];
    var _libraw_dcraw_make_mem_image = Module2["_libraw_dcraw_make_mem_image"] = wasmExports["ka"];
    var _libraw_dcraw_make_mem_thumb = Module2["_libraw_dcraw_make_mem_thumb"] = wasmExports["la"];
    var _libraw_dcraw_clear_mem = Module2["_libraw_dcraw_clear_mem"] = wasmExports["ma"];
    var _libraw_raw2image = Module2["_libraw_raw2image"] = wasmExports["na"];
    var _libraw_get_decoder_info = Module2["_libraw_get_decoder_info"] = wasmExports["oa"];
    var _libraw_COLOR = Module2["_libraw_COLOR"] = wasmExports["pa"];
    var _libraw_set_demosaic = Module2["_libraw_set_demosaic"] = wasmExports["qa"];
    var _libraw_set_output_color = Module2["_libraw_set_output_color"] = wasmExports["ra"];
    var _libraw_set_adjust_maximum_thr = Module2["_libraw_set_adjust_maximum_thr"] = wasmExports["sa"];
    var _libraw_set_output_bps = Module2["_libraw_set_output_bps"] = wasmExports["ta"];
    var _libraw_set_user_mul = Module2["_libraw_set_user_mul"] = wasmExports["ua"];
    var _libraw_set_gamma = Module2["_libraw_set_gamma"] = wasmExports["va"];
    var _libraw_set_no_auto_bright = Module2["_libraw_set_no_auto_bright"] = wasmExports["wa"];
    var _libraw_set_bright = Module2["_libraw_set_bright"] = wasmExports["xa"];
    var _libraw_set_highlight = Module2["_libraw_set_highlight"] = wasmExports["ya"];
    var _libraw_set_fbdd_noiserd = Module2["_libraw_set_fbdd_noiserd"] = wasmExports["za"];
    var _libraw_get_raw_height = Module2["_libraw_get_raw_height"] = wasmExports["Aa"];
    var _libraw_get_raw_width = Module2["_libraw_get_raw_width"] = wasmExports["Ba"];
    var _libraw_get_iheight = Module2["_libraw_get_iheight"] = wasmExports["Ca"];
    var _libraw_get_iwidth = Module2["_libraw_get_iwidth"] = wasmExports["Da"];
    var _libraw_get_cam_mul = Module2["_libraw_get_cam_mul"] = wasmExports["Ea"];
    var _libraw_get_pre_mul = Module2["_libraw_get_pre_mul"] = wasmExports["Fa"];
    var _libraw_get_rgb_cam = Module2["_libraw_get_rgb_cam"] = wasmExports["Ga"];
    var _libraw_get_color_maximum = Module2["_libraw_get_color_maximum"] = wasmExports["Ha"];
    var _libraw_get_raw_image = Module2["_libraw_get_raw_image"] = wasmExports["Ia"];
    var _libraw_get_thumbnail = Module2["_libraw_get_thumbnail"] = wasmExports["Ja"];
    var _libraw_get_shootinginfo = Module2["_libraw_get_shootinginfo"] = wasmExports["Ka"];
    var _libraw_get_makernotes = Module2["_libraw_get_makernotes"] = wasmExports["La"];
    var _libraw_get_canon_makernotes = Module2["_libraw_get_canon_makernotes"] = wasmExports["Ma"];
    var _libraw_get_nikon_makernotes = Module2["_libraw_get_nikon_makernotes"] = wasmExports["Na"];
    var _libraw_get_hasselblad_makernotes = Module2["_libraw_get_hasselblad_makernotes"] = wasmExports["Oa"];
    var _libraw_get_fuji_info = Module2["_libraw_get_fuji_info"] = wasmExports["Pa"];
    var _libraw_get_olympus_makernotes = Module2["_libraw_get_olympus_makernotes"] = wasmExports["Qa"];
    var _libraw_get_sony_info = Module2["_libraw_get_sony_info"] = wasmExports["Ra"];
    var _libraw_get_kodak_makernotes = Module2["_libraw_get_kodak_makernotes"] = wasmExports["Sa"];
    var _libraw_get_panasonic_makernotes = Module2["_libraw_get_panasonic_makernotes"] = wasmExports["Ta"];
    var _libraw_get_pentax_makernotes = Module2["_libraw_get_pentax_makernotes"] = wasmExports["Ua"];
    var _libraw_get_phaseone_makernotes = Module2["_libraw_get_phaseone_makernotes"] = wasmExports["Va"];
    var _libraw_get_ricoh_makernotes = Module2["_libraw_get_ricoh_makernotes"] = wasmExports["Wa"];
    var _libraw_get_samsung_makernotes = Module2["_libraw_get_samsung_makernotes"] = wasmExports["Xa"];
    var _libraw_get_common_metadata = Module2["_libraw_get_common_metadata"] = wasmExports["Ya"];
    var _libraw_get_black = Module2["_libraw_get_black"] = wasmExports["Za"];
    var _libraw_get_cblack = Module2["_libraw_get_cblack"] = wasmExports["_a"];
    var _libraw_get_data_maximum = Module2["_libraw_get_data_maximum"] = wasmExports["$a"];
    var _libraw_get_cam_xyz = Module2["_libraw_get_cam_xyz"] = wasmExports["ab"];
    var _libraw_get_active_height = Module2["_libraw_get_active_height"] = wasmExports["bb"];
    var _libraw_get_active_width = Module2["_libraw_get_active_width"] = wasmExports["cb"];
    var _libraw_get_black_level = Module2["_libraw_get_black_level"] = wasmExports["db"];
    var _libraw_get_bottom_margin = Module2["_libraw_get_bottom_margin"] = wasmExports["eb"];
    var _libraw_get_cdesc = Module2["_libraw_get_cdesc"] = wasmExports["fb"];
    var _libraw_get_cmatrix = Module2["_libraw_get_cmatrix"] = wasmExports["gb"];
    var _libraw_get_color3_image = Module2["_libraw_get_color3_image"] = wasmExports["hb"];
    var _libraw_get_color4_image = Module2["_libraw_get_color4_image"] = wasmExports["ib"];
    var _libraw_get_colors = Module2["_libraw_get_colors"] = wasmExports["jb"];
    var _libraw_get_filters = Module2["_libraw_get_filters"] = wasmExports["kb"];
    var _libraw_get_flip = Module2["_libraw_get_flip"] = wasmExports["lb"];
    var _libraw_get_is_foveon = Module2["_libraw_get_is_foveon"] = wasmExports["mb"];
    var _libraw_get_left_margin = Module2["_libraw_get_left_margin"] = wasmExports["nb"];
    var _libraw_get_linear_max = Module2["_libraw_get_linear_max"] = wasmExports["ob"];
    var _libraw_get_pixel_aspect = Module2["_libraw_get_pixel_aspect"] = wasmExports["pb"];
    var _libraw_get_raw_pitch = Module2["_libraw_get_raw_pitch"] = wasmExports["qb"];
    var _libraw_get_right_margin = Module2["_libraw_get_right_margin"] = wasmExports["rb"];
    var _libraw_get_top_margin = Module2["_libraw_get_top_margin"] = wasmExports["sb"];
    var _libraw_set_half_size = Module2["_libraw_set_half_size"] = wasmExports["tb"];
    var _libraw_set_use_camera_wb = Module2["_libraw_set_use_camera_wb"] = wasmExports["ub"];
    var _free = Module2["_free"] = wasmExports["vb"];
    var _malloc = Module2["_malloc"] = wasmExports["wb"];
    var _libraw_strerror = Module2["_libraw_strerror"] = wasmExports["xb"];
    var _setThrew = wasmExports["yb"];
    var __emscripten_tempret_set = wasmExports["zb"];
    var __emscripten_stack_restore = wasmExports["Ab"];
    var _emscripten_stack_get_current = wasmExports["Bb"];
    var ___cxa_increment_exception_refcount = wasmExports["Cb"];
    var ___cxa_decrement_exception_refcount = wasmExports["Db"];
    var ___cxa_can_catch = wasmExports["Eb"];
    var ___cxa_get_exception_ptr = wasmExports["Fb"];
    function invoke_iii(index, a1, a2) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_ii(index, a1) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_viiijii(index, a1, a2, a3, a4, a5, a6) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3, a4, a5, a6);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_v(index) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)();
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_viiiii(index, a1, a2, a3, a4, a5) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3, a4, a5);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_iiiii(index, a1, a2, a3, a4) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3, a4);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_vi(index, a1) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_iiji(index, a1, a2, a3) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_iiiijjii(index, a1, a2, a3, a4, a5, a6, a7) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3, a4, a5, a6, a7);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_viii(index, a1, a2, a3) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_vii(index, a1, a2) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_iiiiiii(index, a1, a2, a3, a4, a5, a6) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3, a4, a5, a6);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_viiii(index, a1, a2, a3, a4) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3, a4);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_viiiiii(index, a1, a2, a3, a4, a5, a6) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3, a4, a5, a6);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_iiii(index, a1, a2, a3) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_vifff(index, a1, a2, a3, a4) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3, a4);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_ji(index, a1) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
        return 0n;
      }
    }
    function invoke_viff(index, a1, a2, a3) {
      var sp = stackSave();
      try {
        getWasmTableEntry(index)(a1, a2, a3);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_dii(index, a1, a2) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_iiiiiiiii(index, a1, a2, a3, a4, a5, a6, a7, a8) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3, a4, a5, a6, a7, a8);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function invoke_diii(index, a1, a2, a3) {
      var sp = stackSave();
      try {
        return getWasmTableEntry(index)(a1, a2, a3);
      } catch (e) {
        stackRestore(sp);
        if (e !== e + 0) throw e;
        _setThrew(1, 0);
      }
    }
    function run() {
      if (runDependencies > 0) {
        dependenciesFulfilled = run;
        return;
      }
      preRun();
      if (runDependencies > 0) {
        dependenciesFulfilled = run;
        return;
      }
      function doRun() {
        Module2["calledRun"] = true;
        if (ABORT) return;
        initRuntime();
        readyPromiseResolve(Module2);
        Module2["onRuntimeInitialized"]?.();
        postRun();
      }
      if (Module2["setStatus"]) {
        Module2["setStatus"]("Running...");
        setTimeout(() => {
          setTimeout(() => Module2["setStatus"](""), 1);
          doRun();
        }, 1);
      } else {
        doRun();
      }
    }
    function preInit() {
      if (Module2["preInit"]) {
        if (typeof Module2["preInit"] == "function") Module2["preInit"] = [Module2["preInit"]];
        while (Module2["preInit"].length > 0) {
          Module2["preInit"].shift()();
        }
      }
    }
    preInit();
    run();
    moduleRtn = readyPromise;
    return moduleRtn;
  });
})();
var libraw_default = Module;

// node_modules/@colorhythm/libraw-wasm/dist/index.js
var imgother_t = libraw_imgother_t().override("desc", sizedCharArrayAsString(512)).override("artist", sizedCharArrayAsString(64));
var iparams_t = libraw_iparams_t().override("make", sizedCharArrayAsString(64)).override("model", sizedCharArrayAsString(64)).override("software", sizedCharArrayAsString(64)).override("normalized_make", sizedCharArrayAsString(64)).override("normalized_model", sizedCharArrayAsString(64)).override("cdesc", sizedCharArrayAsString(5)).override("xmpdata", charPointerAsString());
var makernotes_lens_t = libraw_makernotes_lens_t().override("Lens", sizedCharArrayAsString(128)).override("body", sizedCharArrayAsString(64)).override("FocalType", enumLike(i16, {
  unknown: 0,
  "fixed focal": 1,
  zoom: 2
})).override("LensFeatures_pre", sizedCharArrayAsString(16)).override("LensFeatures_suf", sizedCharArrayAsString(16)).override("Teleconverter", sizedCharArrayAsString(128)).override("Adapter", sizedCharArrayAsString(128)).override("Attachment", sizedCharArrayAsString(128));
var lensinfo_t = libraw_lensinfo_t().override("LensMake", sizedCharArrayAsString(128)).override("Lens", sizedCharArrayAsString(128)).override("LensSerial", sizedCharArrayAsString(128)).override("InternalLensSerial", sizedCharArrayAsString(128)).override("makernotes", makernotes_lens_t);
var processed_image_t = libraw_processed_image_t().override("data", {
  size: 1,
  read(opts, ctx) {
    const offset = opts.offset ?? 0;
    const size = ctx.data_size;
    return opts.buf.slice(offset, offset + size);
  }
});
var shootinginfo_t = libraw_shootinginfo_t().override("BodySerial", sizedCharArrayAsString(64)).override("InternalBodySerial", sizedCharArrayAsString(64));
var makernotes_t = libraw_makernotes_t();
var thumbnail_t = libraw_thumbnail_t().override("thumb", pointerArrayFromLengthField(u8, "tlength"));
var LibRawError = class extends Error {
  code;
  constructor(code, message) {
    super(message);
    this.code = code;
    this.name = "LibRawError";
  }
};
var LibRaw = class _LibRaw {
  static modulePromise;
  static module;
  lr = 0;
  inputPtr = 0;
  _status = "loading";
  get status() {
    return this._status;
  }
  constructor() {
    this.setup();
  }
  static async initialize(wasm) {
    if (_LibRaw.modulePromise === void 0) {
      const mod = libraw_default({
        instantiateWasm: _LibRaw.createInstantiateWasm(wasm)
      });
      _LibRaw.modulePromise = mod;
      _LibRaw.module = await mod;
    }
    return await _LibRaw.modulePromise;
  }
  static createInstantiateWasm(wasm) {
    if (wasm === void 0)
      return void 0;
    return async (importObject, cb) => {
      const wasmResponse = await wasm;
      const instantiated = await (wasmResponse instanceof Response ? WebAssembly.instantiateStreaming(wasmResponse, importObject) : WebAssembly.instantiate(wasmResponse, importObject));
      cb(instantiated.instance, instantiated.module);
    };
  }
  async waitUntilReady() {
    await _LibRaw.modulePromise;
  }
  async setup() {
    await _LibRaw.initialize();
    this._status = "ready";
    this.lr ||= _LibRaw.module._libraw_init(0);
  }
  open(buffer) {
    if (buffer.byteLength === 0) {
      throw new RangeError("Cannot open an empty camera-raw buffer");
    }
    this.recycle();
    const dataPtr = _LibRaw.module._malloc(buffer.byteLength);
    if (!dataPtr) {
      throw new Error(`Unable to allocate ${buffer.byteLength} bytes for camera-raw input`);
    }
    try {
      const dataHeap = new Uint8Array(_LibRaw.module.HEAPU8.buffer, dataPtr, buffer.byteLength);
      dataHeap.set(new Uint8Array(buffer));
      this.handleError(_LibRaw.module._libraw_open_buffer(this.lr, dataPtr, buffer.byteLength));
      this.inputPtr = dataPtr;
    } catch (error) {
      _LibRaw.module._libraw_recycle(this.lr);
      _LibRaw.module._free(dataPtr);
      throw error;
    }
  }
  unpack() {
    this.handleError(_LibRaw.module._libraw_unpack(this.lr));
  }
  unpackThumb() {
    this.handleError(_LibRaw.module._libraw_unpack_thumb(this.lr));
  }
  unpackThumbEx(i) {
    this.handleError(_LibRaw.module._libraw_unpack_thumb_ex(this.lr, i));
  }
  raw2image() {
    this.handleError(_LibRaw.module._libraw_raw2image(this.lr));
  }
  dcrawProcess() {
    this.handleError(_LibRaw.module._libraw_dcraw_process(this.lr));
  }
  dcrawMakeMemImage() {
    const errcPtr = _LibRaw.module._malloc(4);
    const ptr2 = _LibRaw.module._libraw_dcraw_make_mem_image(this.lr, errcPtr);
    const code = this.readI32(errcPtr);
    _LibRaw.module._free(errcPtr);
    if (!ptr2) {
      this.handleError(code);
      throw new Error("LibRaw did not return a processed image");
    }
    const ret = this.readProcessedImage(ptr2);
    _LibRaw.module._libraw_dcraw_clear_mem(ptr2);
    return ret;
  }
  dcrawMakeMemThumb() {
    const errcPtr = _LibRaw.module._malloc(4);
    const ptr2 = _LibRaw.module._libraw_dcraw_make_mem_thumb(this.lr, errcPtr);
    const code = this.readI32(errcPtr);
    _LibRaw.module._free(errcPtr);
    this.handleError(code);
    if (!ptr2)
      throw new Error("Unexpected error");
    const ret = this.readProcessedImage(ptr2);
    _LibRaw.module._libraw_dcraw_clear_mem(ptr2);
    return ret;
  }
  readProcessedImage(processed) {
    return processed_image_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: processed
    });
  }
  readRawPixels(ptr2, channels) {
    if (!ptr2)
      return null;
    const height = this.getRawHeight();
    const rowLength = this.getRawWidth() * channels;
    const pitch = this.getRawPitch();
    const stride = pitch ? pitch / Uint16Array.BYTES_PER_ELEMENT : rowLength;
    if (!Number.isInteger(stride) || stride < rowLength) {
      throw new Error(`Raw pitch ${pitch} bytes cannot contain ${rowLength} 16-bit values`);
    }
    const source = new Uint16Array(_LibRaw.module.HEAPU8.buffer, ptr2, stride * height);
    if (stride === rowLength)
      return source.slice();
    const pixels = new Uint16Array(rowLength * height);
    for (let row = 0; row < height; row++) {
      const start = row * stride;
      pixels.set(source.subarray(start, start + rowLength), row * rowLength);
    }
    return pixels;
  }
  getActiveHeight() {
    return _LibRaw.module._libraw_get_active_height(this.lr);
  }
  getActiveWidth() {
    return _LibRaw.module._libraw_get_active_width(this.lr);
  }
  getBlackLevel(index) {
    return _LibRaw.module._libraw_get_black_level(this.lr, index);
  }
  getBottomMargin() {
    return _LibRaw.module._libraw_get_bottom_margin(this.lr);
  }
  getCdesc(index) {
    return _LibRaw.module._libraw_get_cdesc(this.lr, index);
  }
  getCmatrix(i, j) {
    return _LibRaw.module._libraw_get_cmatrix(this.lr, i, j);
  }
  getColors() {
    return _LibRaw.module._libraw_get_colors(this.lr);
  }
  getFilters() {
    return _LibRaw.module._libraw_get_filters(this.lr);
  }
  getFlip() {
    return _LibRaw.module._libraw_get_flip(this.lr);
  }
  getIsFoveon() {
    return Boolean(_LibRaw.module._libraw_get_is_foveon(this.lr));
  }
  getRawHeight() {
    return _LibRaw.module._libraw_get_raw_height(this.lr);
  }
  getRawWidth() {
    return _LibRaw.module._libraw_get_raw_width(this.lr);
  }
  getRawPitch() {
    return _LibRaw.module._libraw_get_raw_pitch(this.lr);
  }
  getIHeight() {
    return _LibRaw.module._libraw_get_iheight(this.lr);
  }
  getIWidth() {
    return _LibRaw.module._libraw_get_iwidth(this.lr);
  }
  getCamMul(index) {
    return _LibRaw.module._libraw_get_cam_mul(this.lr, index);
  }
  getPreMul(index) {
    return _LibRaw.module._libraw_get_pre_mul(this.lr, index);
  }
  getLeftMargin() {
    return _LibRaw.module._libraw_get_left_margin(this.lr);
  }
  getLinearMax(index) {
    return _LibRaw.module._libraw_get_linear_max(this.lr, index);
  }
  getPixelAspect() {
    return _LibRaw.module._libraw_get_pixel_aspect(this.lr);
  }
  getRightMargin() {
    return _LibRaw.module._libraw_get_right_margin(this.lr);
  }
  getTopMargin() {
    return _LibRaw.module._libraw_get_top_margin(this.lr);
  }
  getRgbCam(index1, index2) {
    return _LibRaw.module._libraw_get_rgb_cam(this.lr, index1, index2);
  }
  getColorMaximum() {
    return _LibRaw.module._libraw_get_color_maximum(this.lr);
  }
  getBlack() {
    return _LibRaw.module._libraw_get_black(this.lr);
  }
  getCblack(index) {
    return _LibRaw.module._libraw_get_cblack(this.lr, index);
  }
  getDataMaximum() {
    return _LibRaw.module._libraw_get_data_maximum(this.lr);
  }
  getCamXyz(i, j) {
    return _LibRaw.module._libraw_get_cam_xyz(this.lr, i, j);
  }
  setUserMul(index, val) {
    _LibRaw.module._libraw_set_user_mul(this.lr, index, val);
  }
  setDemosaic(value) {
    _LibRaw.module._libraw_set_demosaic(this.lr, value);
  }
  setAdjustMaximumThr(value) {
    _LibRaw.module._libraw_set_adjust_maximum_thr(this.lr, value);
  }
  setOutputColor(value) {
    _LibRaw.module._libraw_set_output_color(this.lr, value);
  }
  setHalfSize(value) {
    _LibRaw.module._libraw_set_half_size(this.lr, value);
  }
  setUseCameraWb(value) {
    _LibRaw.module._libraw_set_use_camera_wb(this.lr, value);
  }
  setOutputBps(value) {
    _LibRaw.module._libraw_set_output_bps(this.lr, value);
  }
  setGamma(index, value) {
    _LibRaw.module._libraw_set_gamma(this.lr, index, value);
  }
  setNoAutoBright(value) {
    _LibRaw.module._libraw_set_no_auto_bright(this.lr, value);
  }
  setBright(value) {
    _LibRaw.module._libraw_set_bright(this.lr, value);
  }
  setHighlight(value) {
    _LibRaw.module._libraw_set_highlight(this.lr, value);
  }
  setFbddNoiserd(value) {
    _LibRaw.module._libraw_set_fbdd_noiserd(this.lr, value);
  }
  static version() {
    if (_LibRaw.module === void 0)
      throw new Error("Not initialized");
    const ptr2 = _LibRaw.module._libraw_version();
    return sizedCharArrayAsString(Number.POSITIVE_INFINITY).read({ buf: _LibRaw.module.HEAPU8, offset: ptr2 }, {});
  }
  static versionNumber() {
    if (_LibRaw.module === void 0)
      throw new Error("Not initialized");
    return _LibRaw.module._libraw_versionNumber();
  }
  static cameraCount() {
    if (_LibRaw.module === void 0)
      throw new Error("Not initialized");
    return _LibRaw.module._libraw_cameraCount();
  }
  static cameraList() {
    if (_LibRaw.module === void 0)
      throw new Error("Not initialized");
    const ptr2 = _LibRaw.module._libraw_cameraList();
    const length = _LibRaw.cameraCount();
    return sizedArray(charPointerAsString(), length).read({ buf: _LibRaw.module.HEAPU8, offset: ptr2 }, {});
  }
  unpackFunctionName() {
    return this.readString(_LibRaw.module._libraw_unpack_function_name(this.lr));
  }
  color(row, col) {
    return _LibRaw.module._libraw_COLOR(this.lr, row, col);
  }
  getColor3Image() {
    const ptr2 = _LibRaw.module._libraw_get_color3_image(this.lr);
    return this.readRawPixels(ptr2, 3);
  }
  getColor4Image() {
    const ptr2 = _LibRaw.module._libraw_get_color4_image(this.lr);
    return this.readRawPixels(ptr2, 4);
  }
  recycle() {
    _LibRaw.module._libraw_recycle(this.lr);
    this.releaseInput();
  }
  getRawImage() {
    const ptr2 = _LibRaw.module._libraw_get_raw_image(this.lr);
    return this.readRawPixels(ptr2, 1);
  }
  getIParams() {
    return iparams_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: _LibRaw.module._libraw_get_iparams(this.lr)
    });
  }
  getLensInfo() {
    return lensinfo_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: _LibRaw.module._libraw_get_lensinfo(this.lr)
    });
  }
  getImgOther() {
    return imgother_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: _LibRaw.module._libraw_get_imgother(this.lr)
    });
  }
  // getDecoderInfo() {
  // 	/**
  // 	 * @see https://github.com/LibRaw/LibRaw/blob/cccb97647fcee56801fa68231fa8a38aa8b52ef7/libraw/libraw_types.h#L120-L124
  // 	 * ```c
  // 	 * typedef struct {
  // 	 *   const char *decoder_name;
  // 	 *   unsigned decoder_flags;
  // 	 * } libraw_decoder_info_t;
  // 	 * ```
  // 	 */
  // 	const decoderInfoPtr = LibRaw.libraw._malloc(8) as LibRawDecoderInfo;
  // 	const code = LibRaw.libraw._libraw_get_decoder_info(decoderInfoPtr);
  // 	console.log({ code });
  // 	if (code) throw this.error(code);
  // 	const ptr = { ptr: decoderInfoPtr };
  // 	return {
  // 		decoderName: this.readString(this.readU32(ptr) as CharPtr),
  // 		decoderFlags: this.readU32(ptr),
  // 	};
  // }
  getThumbnail() {
    return thumbnail_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: _LibRaw.module._libraw_get_thumbnail(this.lr)
    });
  }
  getShootingInfo() {
    return shootinginfo_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: _LibRaw.module._libraw_get_shootinginfo(this.lr)
    });
  }
  getMakernotes() {
    return makernotes_t.read({
      buf: _LibRaw.module.HEAPU8,
      offset: _LibRaw.module._libraw_get_makernotes(this.lr)
    });
  }
  handleError(code) {
    if (code) {
      const message = this.readString(_LibRaw.module._libraw_strerror(code));
      throw new LibRawError(code, message);
    }
  }
  readString(ptr2) {
    if (!ptr2)
      return "";
    return sizedCharArrayAsString(Number.POSITIVE_INFINITY).read({ buf: _LibRaw.module.HEAPU8, offset: ptr2 }, {});
  }
  readI32(ptr2) {
    return readI32({ buf: _LibRaw.module.HEAPU8, offset: ptr2 });
  }
  releaseInput() {
    if (!this.inputPtr)
      return;
    _LibRaw.module._free(this.inputPtr);
    this.inputPtr = 0;
  }
  dispose() {
    if (this._status === "disposed")
      return;
    _LibRaw.module._libraw_close(this.lr);
    this.lr = 0;
    this.releaseInput();
    this._status = "disposed";
  }
  [Symbol.dispose]() {
    this.dispose();
  }
};
export {
  LibRaw,
  LibRawError
};
