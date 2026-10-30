import { prepareMask, maskCoverage } from "./masking.js";

export function blurRadius(settings, width, height) {
  return (
    (Math.max(0, Math.min(100, Number(settings?.amount) || 0)) / 100) *
    Math.min(width, height) *
    0.025
  );
}
export function focusWeight(depth, settings) {
  const focus = (settings.focus ?? 50) / 100,
    range = (settings.range ?? 12) / 100;
  const delta =
    settings.mode === "foreground"
      ? depth - focus
      : settings.mode === "all"
        ? Math.abs(depth - focus)
        : focus - depth;
  return Math.max(0, Math.min(1, (delta - range) / Math.max(0.05, 1 - range)));
}

// Altered adaptation of the 64-tap disk convolution in pmndrs/postprocessing,
// convolution.bokeh.frag (Raoul van Rueschen). See web/vendor/bokeh/LICENSE.txt.
// Added linear-light accumulation, depth/alpha rejection, polygon apertures and tiles.
const vertex = `#version 300 es
in vec2 position;
void main(){gl_Position=vec4(position,0,1);}`;
const fragment = `#version 300 es
precision highp float;
uniform sampler2D image;
uniform sampler2D depthMap;
uniform vec2 imageSize, fullSize, origin;
uniform float radius, focus, focusRange, angle, roundness, edgeProtection;
uniform int useDepth, mode, blades;
out vec4 color;
vec3 linearRGB(vec3 c){return mix(c/12.92,pow((c+.055)/1.055,vec3(2.4)),step(vec3(.04045),c));}
vec3 srgb(vec3 c){c=max(c,vec3(0));return mix(c*12.92,1.055*pow(c,vec3(1./2.4))-.055,step(vec3(.0031308),c));}
float zAt(vec2 pos){return texture(depthMap,clamp((pos+origin)/fullSize,vec2(0),vec2(1))).r;}
float coc(float z){float d=mode==1?z-focus:mode==2?abs(z-focus):focus-z;return clamp((d-focusRange)/max(.05,1.-focusRange),0.,1.);}
void main(){
 vec2 pos=gl_FragCoord.xy;
 vec4 center=texelFetch(image,ivec2(pos),0);
 float z=useDepth==1?zAt(pos):0.;
 float r=radius*(useDepth==1?coc(z):1.);
 if(r<.35||center.a==0.){color=center;return;}
 vec3 sum=linearRGB(center.rgb)*center.a;float total=center.a;
 for(int i=0;i<64;i++){
   float a=float(i)*2.39996323+angle;
   float aperture=1.;
   if(blades>0){float sector=6.283185307/float(blades);aperture=mix(cos(sector*.5)/cos(mod(a-angle+sector*.5,sector)-sector*.5),1.,roundness);}
   vec2 offset=vec2(cos(a),sin(a))*sqrt((float(i)+.5)/64.)*r*aperture;
   vec2 samplePos=clamp(pos+offset,vec2(.5),imageSize-.5);
   vec4 sampleColor=texture(image,samplePos/imageSize);
   float weight=sampleColor.a;
   if(useDepth==1){float other=zAt(samplePos);weight*=mix(1.,1.-smoothstep(.02,.10,other-z),edgeProtection);}
   sum+=linearRGB(sampleColor.rgb)*weight;total+=weight;
 }
 color=vec4(srgb(sum/max(total,.000001)),center.a);
}`;

let renderer;
function createRenderer() {
  if (typeof OffscreenCanvas === "undefined")
    throw new Error("Lens blur requires an OffscreenCanvas-capable browser.");
  const canvas = new OffscreenCanvas(1, 1);
  const gl = canvas.getContext("webgl2", {
    alpha: true,
    premultipliedAlpha: false,
    antialias: false,
    depth: false,
    stencil: false,
    preserveDrawingBuffer: true,
  });
  if (!gl)
    throw new Error("Lens blur requires WebGL 2. Other edits are unchanged.");
  const compile = (type, source) => {
    if (
      gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER, gl.HIGH_FLOAT).precision <
      23
    )
      throw new Error(
        "Lens blur requires high-precision floating-point shaders.",
      );
    gl.disable(gl.DITHER);
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS))
      throw new Error(
        "Lens blur shader could not compile: " + gl.getShaderInfoLog(shader),
      );
    return shader;
  };
  const program = gl.createProgram();
  const shaders = [
    compile(gl.VERTEX_SHADER, vertex),
    compile(gl.FRAGMENT_SHADER, fragment),
  ];
  shaders.forEach((shader) => gl.attachShader(program, shader));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS))
    throw new Error("Lens blur shader could not link.");
  shaders.forEach((shader) => gl.deleteShader(shader));
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(
    gl.ARRAY_BUFFER,
    new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
    gl.STATIC_DRAW,
  );
  const position = gl.getAttribLocation(program, "position");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  const uniforms = new Map();
  for (const name of [
    "image",
    "depthMap",
    "imageSize",
    "fullSize",
    "origin",
    "radius",
    "focus",
    "focusRange",
    "angle",
    "roundness",
    "edgeProtection",
    "useDepth",
    "mode",
    "blades",
  ])
    uniforms.set(name, gl.getUniformLocation(program, name));
  const textures = [gl.createTexture(), gl.createTexture()];
  textures.forEach((texture, index) => {
    gl.activeTexture(gl.TEXTURE0 + index);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(
      gl.TEXTURE_2D,
      gl.TEXTURE_MIN_FILTER,
      index ? gl.NEAREST : gl.LINEAR,
    );
    gl.texParameteri(
      gl.TEXTURE_2D,
      gl.TEXTURE_MAG_FILTER,
      index ? gl.NEAREST : gl.LINEAR,
    );
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  });
  gl.uniform1i(uniforms.get("image"), 0);
  gl.uniform1i(uniforms.get("depthMap"), 1);
  return { canvas, gl, uniforms, textures };
}

function renderBlur(data, width, height, settings, depth) {
  renderer ??= createRenderer();
  const { canvas, gl, uniforms: u, textures } = renderer;
  if (gl.isContextLost()) {
    renderer = null;
    throw new Error(
      "Lens blur graphics context was lost. Turn blur off or try again.",
    );
  }
  const radius = blurRadius(settings, width, height),
    pad = Math.ceil(radius) + 2,
    tile = 768;
  if (pad > 512)
    throw new Error("Lens blur radius exceeds the safe rendering limit.");
  const output = new Uint8ClampedArray(data.length);
  gl.activeTexture(gl.TEXTURE1);
  gl.bindTexture(gl.TEXTURE_2D, textures[1]);
  gl.texImage2D(
    gl.TEXTURE_2D,
    0,
    gl.R32F,
    depth?.width ?? 1,
    depth?.height ?? 1,
    0,
    gl.RED,
    gl.FLOAT,
    depth?.values ?? new Float32Array([0]),
  );
  gl.uniform2f(u.get("fullSize"), width, height);
  gl.uniform1f(u.get("radius"), radius);
  gl.uniform1f(u.get("focus"), (settings.focus ?? 50) / 100);
  gl.uniform1f(u.get("focusRange"), (settings.range ?? 12) / 100);
  gl.uniform1f(u.get("angle"), ((settings.angle ?? 0) * Math.PI) / 180);
  gl.uniform1f(
    u.get("roundness"),
    Math.max(0, Math.min(1, (settings.roundness ?? 0) / 100)),
  );
  gl.uniform1f(
    u.get("edgeProtection"),
    Math.max(0, Math.min(1, (settings.edgeProtection ?? 70) / 100)),
  );
  gl.uniform1i(u.get("useDepth"), depth ? 1 : 0);
  gl.uniform1i(
    u.get("mode"),
    settings.mode === "foreground" ? 1 : settings.mode === "all" ? 2 : 0,
  );
  gl.uniform1i(
    u.get("blades"),
    [5, 6, 7, 8, 9].includes(settings.blades) ? settings.blades : 0,
  );
  for (let y = 0; y < height; y += tile)
    for (let x = 0; x < width; x += tile) {
      const left = Math.max(0, x - pad),
        top = Math.max(0, y - pad),
        right = Math.min(width, x + tile + pad),
        bottom = Math.min(height, y + tile + pad);
      const w = right - left,
        h = bottom - top;
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
      const pixels = new Uint8Array(w * h * 4);
      for (let row = 0; row < h; row++)
        pixels.set(
          data.subarray(
            ((top + row) * width + left) * 4,
            ((top + row) * width + right) * 4,
          ),
          row * w * 4,
        );
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, textures[0]);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA8,
        w,
        h,
        0,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        pixels,
      );
      gl.uniform2f(u.get("imageSize"), w, h);
      gl.uniform2f(u.get("origin"), left, top);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      const tw = Math.min(tile, width - x),
        th = Math.min(tile, height - y),
        read = new Uint8Array(tw * th * 4);
      gl.readPixels(x - left, y - top, tw, th, gl.RGBA, gl.UNSIGNED_BYTE, read);
      if (gl.getError() !== gl.NO_ERROR)
        throw new Error(
          "Lens blur exceeded the graphics limits. Other edits are unchanged.",
        );
      for (let row = 0; row < th; row++)
        output.set(
          read.subarray(row * tw * 4, (row + 1) * tw * 4),
          ((y + row) * width + x) * 4,
        );
    }
  // Release the large texture storage while keeping compiled shader state reusable.
  gl.texImage2D(
    gl.TEXTURE_2D,
    0,
    gl.RGBA8,
    1,
    1,
    0,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    new Uint8Array(4),
  );
  canvas.width = canvas.height = 1;
  return output;
}

export function applyLensBlur(
  data,
  width,
  height,
  edits,
  depth = null,
  maxPixels = 24_000_000,
) {
  const scopes = [
    { settings: edits.lensBlur },
    ...(edits.masks ?? [])
      .filter((mask) => mask.enabled)
      .map((mask) => ({ settings: mask.adjustments?.lensBlur, mask })),
  ].filter(({ settings }) => settings?.enabled && settings.amount > 0);
  if (!scopes.length) return data;
  if (width * height > maxPixels)
    throw new Error(
      "Lens blur is above this device's safe image limit. Disable blur for full-resolution export.",
    );
  let result = data;
  for (const { settings, mask } of scopes) {
    const map = mask ? null : depth;
    if (!mask && !map)
      throw new Error(
        "Analyze scene depth before enabling whole-photo lens blur.",
      );
    const blurred = renderBlur(result, width, height, settings, map);
    if (!mask) {
      result = blurred;
      continue;
    }
    const prepared = prepareMask(mask),
      rgb = [0, 0, 0];
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) {
        const i = (y * width + x) * 4;
        rgb[0] = data[i];
        rgb[1] = data[i + 1];
        rgb[2] = data[i + 2];
        const coverage = maskCoverage(
          prepared,
          (x + 0.5) / width,
          (y + 0.5) / height,
          rgb,
        );
        for (let c = 0; c < 3; c++)
          blurred[i + c] =
            result[i + c] + (blurred[i + c] - result[i + c]) * coverage;
      }
    result = blurred;
  }
  return result;
}
