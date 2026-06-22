// Plain data class for the user returned from mobile_login.
// Matches the shape returned by _user_profile() in auth.py.
 
class UserModel {
  final String email;
  final String fullName;
  final String? userImage;
  final List<String> roles;
  final String primaryRole;
  final bool enabled;
  final String language;
  final String timeZone;
 
  const UserModel({
    required this.email,
    required this.fullName,
    this.userImage,
    required this.roles,
    required this.primaryRole,
    required this.enabled,
    required this.language,
    required this.timeZone,
  });
 
  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      email:       json['user']?.toString() ?? json['email']?.toString() ?? '',
      fullName:    json['full_name']?.toString() ?? '',
      userImage:   json['user_image']?.toString(),
      roles:       (json['roles'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      primaryRole: json['primary_role']?.toString() ?? 'viewer',
      enabled:     json['enabled'] == 1 || json['enabled'] == true,
      language:    json['language']?.toString() ?? 'en',
      timeZone:    json['time_zone']?.toString() ?? 'Africa/Dar_es_Salaam',
    );
  }
 
  /// Convenience: is this user an admin shell candidate?
  bool get isAdmin => primaryRole == 'admin';
 
  /// Convenience: any of the consumer roles
  bool get isStudent  => roles.contains('Student');
  bool get isLecturer => roles.contains('Lecturer');
  bool get isCR       => roles.contains('Class Representative (CR)');
  bool get isDeptAdmin=> roles.contains('Department Admin');
 
  Map<String, dynamic> toJson() => {
        'email':        email,
        'full_name':    fullName,
        'user_image':   userImage,
        'roles':        roles,
        'primary_role': primaryRole,
        'enabled':      enabled,
        'language':     language,
        'time_zone':    timeZone,
      };
}