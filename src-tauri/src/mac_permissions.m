#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>

/**
 * Check current macOS microphone authorization status.
 * Returns:
 *   0 = NotDetermined
 *   1 = Restricted
 *   2 = Denied
 *   3 = Authorized
 */
int mac_check_microphone_permission(void) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    return (int)status;
}

/**
 * Request macOS microphone permission. If status is NotDetermined, displays
 * the native macOS TCC prompt ("WhisperProtocol would like to access the microphone").
 * Returns:
 *   0 = NotDetermined (timed out)
 *   1 = Restricted
 *   2 = Denied
 *   3 = Authorized
 */
int mac_request_microphone_permission(void) {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (status == AVAuthorizationStatusAuthorized) {
        return 3;
    }
    if (status == AVAuthorizationStatusDenied || status == AVAuthorizationStatusRestricted) {
        return (int)status;
    }

    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block BOOL granted_result = NO;

    [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL granted) {
        granted_result = granted;
        dispatch_semaphore_signal(sem);
    }];

    // Wait up to 30 seconds for user to respond to the dialog
    dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, 30 * NSEC_PER_SEC));
    return granted_result ? 3 : 2;
}
