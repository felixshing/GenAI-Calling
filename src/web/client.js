// get DOM elements
var dataChannelLog = document.getElementById('data-channel'),
    iceConnectionLog = document.getElementById('ice-connection-state'),
    iceGatheringLog = document.getElementById('ice-gathering-state'),
    signalingLog = document.getElementById('signaling-state');

// peer connection
var pc = null;

// data channel
var dc = null, dcInterval = null;

// Generate a unique session ID for this browser session
var sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
console.log('Client session ID:', sessionId);

// Add debugging function
function debugLog(message) {
    console.log('[DEBUG]', message);
    dataChannelLog.textContent += '[DEBUG] ' + message + '\n';
}

function createPeerConnection() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        config.iceServers = [{ urls: ['stun:stun.l.google.com:19302'] }];
    }

    pc = new RTCPeerConnection(config);

    // Add bidirectional audio transceiver for both sending speech and receiving responses
    // sendrecv = client can both send TO server and receive FROM server
    pc.addTransceiver('audio', { direction: 'sendrecv' });

    // register some listeners to help debugging
    pc.addEventListener('icegatheringstatechange', () => {
        iceGatheringLog.textContent += ' -> ' + pc.iceGatheringState;
    }, false);
    iceGatheringLog.textContent = pc.iceGatheringState;

    pc.addEventListener('iceconnectionstatechange', () => {
        iceConnectionLog.textContent += ' -> ' + pc.iceConnectionState;
    }, false);
    iceConnectionLog.textContent = pc.iceConnectionState;

    pc.addEventListener('signalingstatechange', () => {
        signalingLog.textContent += ' -> ' + pc.signalingState;
    }, false);
    signalingLog.textContent = pc.signalingState;

    // connect audio / video
    pc.addEventListener('track', (evt) => {
        if (evt.track.kind == 'video') {
            document.getElementById('video').srcObject = evt.streams[0];
        } else {
            const audioElement = document.getElementById('audio');
            const statusElement = document.getElementById('audio-status');
            
            console.log('🎵 Received audio track from server');
            statusElement.innerHTML = '🎵 Audio track received from server';
            
            audioElement.srcObject = evt.streams[0];
            
            // Add event listeners for audio debugging
            audioElement.addEventListener('loadstart', () => {
                console.log('🎵 Audio loading started');
                statusElement.innerHTML += '<br>📡 Audio loading started';
            });
            
            audioElement.addEventListener('canplay', () => {
                console.log('🎵 Audio can start playing');
                statusElement.innerHTML += '<br>Audio ready to play';
            });
            
            audioElement.addEventListener('play', () => {
                console.log('🎵 Audio started playing');
                statusElement.innerHTML += '<br>🔊 Audio PLAYING!';
            });
            
            audioElement.addEventListener('pause', () => {
                console.log('🎵 Audio paused');
                statusElement.innerHTML += '<br>⏸️ Audio paused';
            });
            
            // Try to play audio (handle autoplay restrictions)
            audioElement.play().then(() => {
                console.log('🎵 Audio play() succeeded');
                statusElement.innerHTML += '<br> Autoplay succeeded';
            }).catch((error) => {
                console.log('🎵 Audio play() failed:', error);
                statusElement.innerHTML += '<br> Autoplay blocked - ' + error.message;
                statusElement.innerHTML += '<br> Click audio controls to play manually';
            });
        }
    });

    return pc;
}

function enumerateInputDevices() {
    const populateSelect = (select, devices) => {
        let counter = 1;
        devices.forEach((device) => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.text = device.label || ('Device #' + counter);
            select.appendChild(option);
            counter += 1;
        });
    };

    navigator.mediaDevices.enumerateDevices().then((devices) => {
        populateSelect(
            document.getElementById('audio-input'),
            devices.filter((device) => device.kind == 'audioinput')
        );
        populateSelect(
            document.getElementById('video-input'),
            devices.filter((device) => device.kind == 'videoinput')
        );
    }).catch((e) => {
        alert(e);
    });
}

function negotiate() {
    debugLog('Starting negotiation...');
    debugLog('Data channel state before negotiation: ' + (dc ? dc.readyState : 'null'));
    return pc.createOffer().then((offer) => {
        return pc.setLocalDescription(offer);
    }).then(() => {
        // wait for ICE gathering to complete
        return new Promise((resolve) => {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                function checkState() {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                }
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(() => {
        var offer = pc.localDescription;
        var codec;

        codec = document.getElementById('audio-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('audio', codec, offer.sdp);
        }

        codec = document.getElementById('video-codec').value;
        if (codec !== 'default') {
            offer.sdp = sdpFilterCodec('video', codec, offer.sdp);
        }

        document.getElementById('offer-sdp').textContent = offer.sdp;
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
                video_transform: document.getElementById('video-transform').value,
                session_id: sessionId
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then((response) => {
        return response.json();
    }).then((answer) => {
        document.getElementById('answer-sdp').textContent = answer.sdp;
        return pc.setRemoteDescription(answer);
    }).then(() => {
        debugLog('Negotiation completed successfully');
        debugLog('Data channel state after negotiation: ' + (dc ? dc.readyState : 'null'));
    }).catch((e) => {
        debugLog('Negotiation failed: ' + e);
        alert(e);
    });
}

/*
function start() {
    document.getElementById('start').style.display = 'none';

    pc = createPeerConnection();

    var time_start = null;

    const current_stamp = () => {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    };

    if (document.getElementById('use-datachannel').checked) {
        var parameters = JSON.parse(document.getElementById('datachannel-parameters').value);

        dc = pc.createDataChannel('chat', parameters);
        dc.addEventListener('close', () => {
            clearInterval(dcInterval);
            dataChannelLog.textContent += '- close\n';
        });
        dc.addEventListener('open', () => {
            dataChannelLog.textContent += '- open\n';
            dcInterval = setInterval(() => {
                var message = 'ping ' + current_stamp();
                dataChannelLog.textContent += '> ' + message + '\n';
                dc.send(message);
            }, 1000);
        });
        dc.addEventListener('message', (evt) => {
            dataChannelLog.textContent += '< ' + evt.data + '\n';

            if (evt.data.substring(0, 4) === 'pong') {
                var elapsed_ms = current_stamp() - parseInt(evt.data.substring(5), 10);
                dataChannelLog.textContent += ' RTT ' + elapsed_ms + ' ms\n';
            }
        });
    }

    // Build media constraints.

    const constraints = {
        audio: false,
        video: false
    };

    if (document.getElementById('use-audio').checked) {
        const audioConstraints = {};

        const device = document.getElementById('audio-input').value;
        if (device) {
            audioConstraints.deviceId = { exact: device };
        }

        constraints.audio = Object.keys(audioConstraints).length ? audioConstraints : true;
    }

    if (document.getElementById('use-video').checked) {
        const videoConstraints = {};

        const device = document.getElementById('video-input').value;
        if (device) {
            videoConstraints.deviceId = { exact: device };
        }

        const resolution = document.getElementById('video-resolution').value;
        if (resolution) {
            const dimensions = resolution.split('x');
            videoConstraints.width = parseInt(dimensions[0], 0);
            videoConstraints.height = parseInt(dimensions[1], 0);
        }

        constraints.video = Object.keys(videoConstraints).length ? videoConstraints : true;
    }

    // Acquire media and start negociation.

    if (constraints.audio || constraints.video) {
        if (constraints.video) {
            document.getElementById('media').style.display = 'block';
        }
        //Here is to capture the live audio and video from the device
        navigator.mediaDevices.getUserMedia(constraints).then((stream) => {
            stream.getTracks().forEach((track) => {
                pc.addTrack(track, stream);
            });
            return negotiate();
        }, (err) => {
            alert('Could not acquire media: ' + err);
        });
    } else {
        negotiate();
    }

    document.getElementById('stop').style.display = 'inline-block';
}
*/

function startCall() {


    document.getElementById('start').style.display = 'none';

    pc = createPeerConnection();

    var time_start = null;

    const current_stamp = () => {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    };

    if (document.getElementById('use-datachannel').checked) {
        var parameters = JSON.parse(document.getElementById('datachannel-parameters').value);

        debugLog('Creating new data channel...');
        dc = pc.createDataChannel('chat', parameters);
        debugLog('Data channel created, readyState: ' + dc.readyState);
        
        dc.addEventListener('close', () => {
            debugLog('Data channel CLOSED!');
            clearInterval(dcInterval);
            dataChannelLog.textContent += '- close\n';
        });
        dc.addEventListener('open', () => {
            debugLog('Data channel OPENED!');
            dataChannelLog.textContent += '- open\n';
            dcInterval = setInterval(() => {
                var message = 'ping ' + current_stamp();
                dataChannelLog.textContent += '> ' + message + '\n';
                if (dc.readyState === 'open') {
                    dc.send(message);
                } else {
                    debugLog('WARNING: Trying to send ping but DC state is: ' + dc.readyState);
                }
            }, 1000);
        });
        dc.addEventListener('message', (evt) => {
            dataChannelLog.textContent += '< ' + evt.data + '\n';

            if (evt.data.substring(0, 4) === 'pong') {
                var elapsed_ms = current_stamp() - parseInt(evt.data.substring(5), 10);
                dataChannelLog.textContent += ' RTT ' + elapsed_ms + ' ms\n';
            } else if (evt.data === 'transcription_received') {
                debugLog('Server confirmed receipt of transcribe_now signal!');
            }
        });
        
        // Add error event listener
        dc.addEventListener('error', (event) => {
            debugLog('Data channel ERROR: ' + event);
        });
    }

    negotiate();                           // offer/answer with no media yet
    document.getElementById('record').style.display = 'inline-block';
    document.getElementById('stop').style.display   = 'inline-block';
}

function stopCall() {
    debugLog('Stopping call - cleaning up UI and connections');
    
    document.getElementById('stop').style.display = 'none';
    document.getElementById('record').style.display = 'none'; // Hide record button
    document.getElementById('start').style.display = 'inline-block'; // Show start button again

    // Reset recording state
    recording = false;
    chunkCounter = 1;
    
    // Stop any active audio recording
    if (localAudioTrack) {
        localAudioTrack.stop();
        localAudioTrack = null;
        debugLog('Stopped local audio track');
    }
    
    // Clear ping interval if still running
    if (dcInterval) {
        debugLog('Clearing ping/pong interval');
        clearInterval(dcInterval);
        dcInterval = null;
    }

    // close data channel
    if (dc) {
        dc.close();
    }

    // close transceivers
    if (pc.getTransceivers) {
        pc.getTransceivers().forEach((transceiver) => {
            if (transceiver.stop) {
                transceiver.stop();
            }
        });
    }

    // close local audio / video
    pc.getSenders().forEach((sender) => {
        sender.track.stop();
    });

    // close peer connection
    setTimeout(() => {
        pc.close();
    }, 500);
}

function sdpFilterCodec(kind, codec, realSdp) {
    var allowed = []
    var rtxRegex = new RegExp('a=fmtp:(\\d+) apt=(\\d+)\r$');
    var codecRegex = new RegExp('a=rtpmap:([0-9]+) ' + escapeRegExp(codec))
    var videoRegex = new RegExp('(m=' + kind + ' .*?)( ([0-9]+))*\\s*$')

    var lines = realSdp.split('\n');

    var isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var match = lines[i].match(codecRegex);
            if (match) {
                allowed.push(parseInt(match[1]));
            }

            match = lines[i].match(rtxRegex);
            if (match && allowed.includes(parseInt(match[2]))) {
                allowed.push(parseInt(match[1]));
            }
        }
    }

    var skipRegex = 'a=(fmtp|rtcp-fb|rtpmap):([0-9]+)';
    var sdp = '';

    isKind = false;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('m=' + kind + ' ')) {
            isKind = true;
        } else if (lines[i].startsWith('m=')) {
            isKind = false;
        }

        if (isKind) {
            var skipMatch = lines[i].match(skipRegex);
            if (skipMatch && !allowed.includes(parseInt(skipMatch[2]))) {
                continue;
            } else if (lines[i].match(videoRegex)) {
                sdp += lines[i].replace(videoRegex, '$1 ' + allowed.join(' ')) + '\n';
            } else {
                sdp += lines[i] + '\n';
            }
        } else {
            sdp += lines[i] + '\n';
        }
    }

    return sdp;
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // $& means the whole matched string
}

var localAudioTrack = null;
var recording = false;
var sender = null;
var chunkCounter = 1;

function updateRecordButton() {
    const label = recording ? `Stop & Transcribe (${chunkCounter})` : `Start Recording (${chunkCounter})`;
    document.getElementById('record').textContent = label;
}

function toggleRecord() {
    console.log('toggleRecord called, recording =', recording);
    debugLog('toggleRecord called, recording = ' + recording);
    debugLog('Data channel state at toggle start: ' + (dc ? dc.readyState : 'null'));
    const btn = document.getElementById('record');

    if (!recording) {                     // ---- start a new chunk ----
        btn.disabled = true;
        navigator.mediaDevices.getUserMedia({ audio:true }).then(stream => {
            localAudioTrack = stream.getAudioTracks()[0];
            debugLog('Got audio stream, adding track to peer connection...');
            debugLog('Data channel state before addTrack: ' + (dc ? dc.readyState : 'null'));
            // Always use addTrack + renegotiate (simplest approach)
            sender = pc.addTrack(localAudioTrack, stream);
            debugLog('Track added, starting renegotiation...');
            return negotiate();

            //For some reaosns, replaceTrack does not work. 
            // if (sender) {
            //     sender.replaceTrack(localAudioTrack);
            //     return Promise.resolve();        // no renegotiation
            // } 
        }).then(() => {
            recording = true;
            btn.disabled = false;
            
            // Stop ping/pong messages once recording starts
            if (dcInterval) {
                debugLog('Stopping ping/pong messages - recording started');
                dataChannelLog.textContent += '[INFO] Ping/pong stopped - recording mode active\n';
                clearInterval(dcInterval);
                dcInterval = null;
            }
            
            updateRecordButton();
        });
    } else {                 // ---- SEND / stop recording ----
        if (localAudioTrack) {
            localAudioTrack.onended = () => console.log('local track ended');
            localAudioTrack.stop();
        }
        
        // Send immediate transcribe signal via data-channel
        console.log('About to check data channel. dc =', dc);
        console.log('dc.readyState =', dc ? dc.readyState : 'dc is null');
        debugLog('Attempting to send transcribe_now signal...');
        debugLog('Data channel state: ' + (dc ? dc.readyState : 'null'));
        if (dc && dc.readyState === 'open') {
            console.log('Sending transcribe_now signal');
            debugLog('Sending transcribe_now signal via data channel');
            dc.send('transcribe_now');
            console.log('transcribe_now signal sent successfully');
            debugLog('transcribe_now signal sent successfully');
        } else {
            console.log('Data channel not open, readyState:', dc ? dc.readyState : 'dc is null');
            debugLog('ERROR: Cannot send transcribe_now - data channel not open!');
        }
        
        recording = false;
        chunkCounter += 1;
        updateRecordButton();
    }
}

enumerateInputDevices();